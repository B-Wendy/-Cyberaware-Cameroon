"""
evaluate.py  —  measures how good the retrieval really is (real numbers, not guesses).

Run from the project folder (after `python ingest.py`):

    python evaluate.py                      # uses evaluation/benchmark.csv
    python evaluate.py --file my_questions.csv
    python evaluate.py --latency 20         # also times 20 full chatbot answers (needs GROQ_API_KEY)

THE BENCHMARK FILE (a CSV with these columns)
    query, language (en/fr/pidgin), expected_topic, kind (in_scope / out_of_scope), source
  * in_scope questions have a known correct topic.  A returned passage counts as
    RELEVANT when its topic equals expected_topic.
  * out_of_scope questions (football, recipes ...) should NOT be answered: the
    chatbot should reject them.

THE NUMBERS
    P@k    precision: of the k passages returned, what share were relevant?
    R@k    recall:    of all relevant passages that exist, what share were returned?
    Hit@k  did at least one relevant passage appear in the top k?
    MRR    mean reciprocal rank: 1/rank of the first relevant passage, averaged
    Answered   in-scope questions that still had at least one passage after the
               similarity threshold (so the chatbot would try to answer them)
    Rejected   out-of-scope questions correctly turned away by the threshold

Replace/extend the benchmark with REAL questions from your survey and re-run:
your dissertation numbers must come from a file like this one.
"""

import argparse
import csv
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from config import MIN_SIMILARITY, TOP_K
from embedder import normalise

DEFAULT_FILE = Path(__file__).parent / "evaluation" / "benchmark.csv"
CORPUS = {"en": "EN", "fr": "FR", "pidgin": "EN"}
EVAL_K = 5


def load_rows(path) -> list:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _ranked(collection, vector, corpus_language, k):
    """Top-k passages for one corpus language, without any threshold."""
    res = collection.query(query_embeddings=[vector], n_results=k,
                           where={"language": corpus_language},
                           include=["documents", "metadatas", "distances"])
    return [(m, 1.0 - float(d)) for m, d in zip(res["metadatas"][0], res["distances"][0])]


def run_benchmark(rows, collection, embedder, threshold=MIN_SIMILARITY, k=EVAL_K) -> dict:
    # number of passages that exist for each (topic, corpus language)
    total = defaultdict(int)
    for m in collection.get(include=["metadatas"])["metadatas"]:
        total[(m["topic"], m["language"])] += 1

    per = defaultdict(lambda: {"p": [], "r": [], "hit": [], "rr": [], "answered": [], "rejected": []})
    for row in rows:
        lang = row["language"].strip().lower()
        corpus = CORPUS.get(lang, "EN")
        vec = embedder.embed(normalise(row["query"]))
        ranked = _ranked(collection, vec, corpus, k) if any(vec) else []
        kept = [1 for _m, s in ranked[:TOP_K] if s >= threshold]
        bucket = per[lang]
        if row["kind"].strip() == "out_of_scope":
            bucket["rejected"].append(0 if kept else 1)
            continue
        relevant_total = total[(row["expected_topic"], corpus)] or 1
        flags = [m["topic"] == row["expected_topic"] for m, _s in ranked]
        hits = sum(flags)
        bucket["p"].append(hits / k)
        bucket["r"].append(hits / relevant_total)
        bucket["hit"].append(1 if hits else 0)
        bucket["rr"].append(next((1 / (i + 1) for i, f in enumerate(flags) if f), 0.0))
        bucket["answered"].append(1 if kept else 0)

    def mean(xs):
        return round(statistics.fmean(xs), 3) if xs else None

    report = {"k": k, "threshold": threshold, "languages": {}}
    overall = defaultdict(list)
    for lang, b in sorted(per.items()):
        report["languages"][lang] = {
            "in_scope_queries": len(b["p"]), "out_of_scope_queries": len(b["rejected"]),
            f"P@{k}": mean(b["p"]), f"R@{k}": mean(b["r"]), f"Hit@{k}": mean(b["hit"]),
            "MRR": mean(b["rr"]), "answered": mean(b["answered"]), "rejected": mean(b["rejected"]),
        }
        for key, vals in b.items():
            overall[key].extend(vals)
    report["overall"] = {
        "in_scope_queries": len(overall["p"]), "out_of_scope_queries": len(overall["rejected"]),
        f"P@{k}": mean(overall["p"]), f"R@{k}": mean(overall["r"]), f"Hit@{k}": mean(overall["hit"]),
        "MRR": mean(overall["rr"]), "answered": mean(overall["answered"]), "rejected": mean(overall["rejected"]),
    }
    return report


def print_report(report: dict):
    k = report["k"]
    print(f"\nRetrieval benchmark   (k={k}, similarity threshold={report['threshold']})\n")
    head = f"{'language':9}{'in':>4}{'out':>5}{'P@'+str(k):>8}{'R@'+str(k):>8}{'Hit@'+str(k):>8}{'MRR':>7}{'Answered':>10}{'Rejected':>10}"
    print(head)
    print("-" * len(head))
    rows = list(report["languages"].items()) + [("OVERALL", report["overall"])]
    for lang, d in rows:
        def f(x): return "  -  " if x is None else f"{x:.2f}"
        print(f"{lang:9}{d['in_scope_queries']:>4}{d['out_of_scope_queries']:>5}{f(d[f'P@{k}']):>8}{f(d[f'R@{k}']):>8}"
              f"{f(d[f'Hit@{k}']):>8}{f(d['MRR']):>7}{f(d['answered']):>10}{f(d['rejected']):>10}")
    print("\nNote: each topic has only a few passages, so P@k cannot be high however good the search is."
          "\nHit@k and MRR are the fairer measures for a corpus this small.")


def measure_latency(n: int, rows) -> dict:
    """Time n complete answers (retrieval + model).  Needs GROQ_API_KEY and internet."""
    from rag import answer_question
    queries = [r for r in rows if r["kind"].strip() == "in_scope"]
    times = []
    for i in range(n):
        row = queries[i % len(queries)]
        start = time.perf_counter()
        answer_question(row["query"], row["language"].strip().lower())
        times.append(time.perf_counter() - start)
    times.sort()
    pct = lambda p: times[min(len(times) - 1, int(round(p * (len(times) - 1))))]
    return {"requests": n, "median_s": round(statistics.median(times), 2),
            "p25_s": round(pct(0.25), 2), "p75_s": round(pct(0.75), 2), "p95_s": round(pct(0.95), 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--threshold", type=float, default=MIN_SIMILARITY)
    ap.add_argument("--latency", type=int, default=0, help="also time N full answers (needs the Groq key)")
    ap.add_argument("--save", default="evaluation/results.json", help="where to save the numbers")
    args = ap.parse_args()

    from rag import get_collection, get_embedder
    rows = load_rows(args.file)
    report = run_benchmark(rows, get_collection(), get_embedder(), threshold=args.threshold)
    print_report(report)
    if args.latency:
        report["latency"] = measure_latency(args.latency, rows)
        print("\nLatency:", report["latency"])
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {args.save}")


if __name__ == "__main__":
    main()
