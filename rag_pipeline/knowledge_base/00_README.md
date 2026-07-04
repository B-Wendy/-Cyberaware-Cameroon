# Knowledge Base — Phase 1 (Knowledge Curation)

## What this is
These files are grounding content for your RAG pipeline. They're based on **real, current** material I pulled from ANTIC's CIRT division (cirt.cm) and ANTIC's main site (antic.cm) — not invented. Each topic file states its source(s) at the top.

**Important:** I did not copy ANTIC/CIRT's published text verbatim (copyright). I rewrote every fact, scenario, and recommendation in original wording, while keeping the facts accurate. This is actually *better* for your RAG pipeline anyway — embeddings work better on clean, consistent prose than on scraped HTML with tables and formatting artifacts.

## Files
- `01_antic_cirt_institutional.md` — what ANTIC/CIRT is, legal basis, real contact channels
- `02_phishing_scams.md` through `08_ransomware_backup.md` — one topic per file, EN + FR sections
- `09_reporting_incidents.md` — step-by-step incident reporting (your Objective 3)
- `faq_dataset.csv` — 30 Q&A pairs (EN/FR) for your evaluation set / few-shot examples
- `sources.md` — every URL cited, for your dissertation bibliography

## Chunking recommendation
Each topic file is already split into EN/FR sections of ~300-450 words — close to your target chunk size. Suggested approach:
1. Split each file on `## EN` / `## FR` headers → 2 chunks per file (one per language)
2. Tag metadata per chunk: `{source, topic, language, last_updated}` — use the frontmatter at the top of each file
3. For files >450 words per language, split further on paragraph breaks

## What's still missing (you should add these)
ANTIC's main site (antic.cm) has **downloadable PDF guides** I couldn't fetch directly (binary files, not crawlable by my tools): "Guide de l'usager / User's Guide", "Guide des enfants / Guide for youths", "Guide des parents / Guide for parents." Go to antic.cm and download these yourself — they'll likely have richer content (especially for the children/parents angle, which could differentiate your project). I'd also recommend:
- A few real ANTIC security bulletins from cirt.cm/bulletins-de-securite/ (shows live threat intel, good for your "common scams" angle)
- Cameroon's Penal Code / Law N°2010/012 full text if you want to cite specific articles (I have the law numbers and general scope, not the full legal text)

## Honesty note for your dissertation
Be upfront in your methodology chapter that the KB combines (a) paraphrased official ANTIC/CIRT guidance with source citations, and (b) generally accepted cybersecurity best practices contextualized for Cameroon. Don't present paraphrased content as a verbatim quote of ANTIC — cite it as "adapted from ANTIC/CIRT-Cameroun guidance, [URL]."
