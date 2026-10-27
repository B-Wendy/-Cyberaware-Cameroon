/**
 * CyberAware Cameroon - user feedback form builder
 *
 * HOW TO USE (5 minutes)
 *   1. Go to https://script.google.com and click "New project".
 *   2. Delete the code that is already there, then paste ALL of this file.
 *   3. Click the Save icon, then press "Run" (function: createFeedbackForm).
 *   4. Google asks for permission the first time: choose your account,
 *      "Advanced", "Go to project", "Allow".
 *   5. Open "Execution log" at the bottom. It prints three links:
 *      - the link to SEND to people (the form),
 *      - the link to EDIT the form,
 *      - the link to the spreadsheet where the answers collect.
 *   6. Fill the form once yourself to test it, then delete that test row
 *      in the spreadsheet.
 *
 * The form is anonymous: no name, phone number or e-mail is asked.
 * Every question is shown in English and in French.
 * The ten usability statements are the standard System Usability Scale (SUS).
 */

function bi(en, fr) { return en + ' / ' + fr; }

function createFeedbackForm() {
  var form = FormApp.create('CyberAware Cameroon - User Feedback / Avis des utilisateurs');

  form.setDescription(
    'This short form is part of a final-year research project at ICT University, Cameroon. ' +
    'It takes about 5 minutes. Taking part is voluntary and anonymous: please do NOT write your name, ' +
    'phone number or address. You may stop at any time. There is no payment. ' +
    'Your answers are used only for the research report.\n\n' +
    'Ce court formulaire fait partie d’un projet de fin d’études à ICT University, Cameroun. ' +
    'Il prend environ 5 minutes. La participation est volontaire et anonyme : n’écrivez PAS votre nom, ' +
    'votre numéro de téléphone ni votre adresse. Vous pouvez arrêter à tout moment. Il n’y a aucun paiement. ' +
    'Vos réponses servent uniquement au rapport de recherche.');
  form.setProgressBar(true);
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage('Thank you! / Merci beaucoup !');

  // 1. Consent
  form.addCheckboxItem()
    .setTitle(bi('Consent', 'Consentement'))
    .setChoiceValues([bi('I am 18 or older and I agree to take part',
                         'J’ai 18 ans ou plus et j’accepte de participer')])
    .setRequired(true);

  // 2. About you
  form.addPageBreakItem().setTitle(bi('About you', 'À propos de vous'));

  form.addMultipleChoiceItem()
    .setTitle(bi('Have you used CyberAware Cameroon before?', 'Avez-vous déjà utilisé CyberAware Cameroon ?'))
    .setChoiceValues([
      bi('Yes, in July or August', 'Oui, en juillet ou août'),
      bi('No, this is my first time', 'Non, c’est la première fois')])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle(bi('Your age', 'Votre âge'))
    .setChoiceValues(['18-25', '26-35', '36-45', '46-55', bi('56 or older', '56 ans ou plus')])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle(bi('What do you do?', 'Que faites-vous ?'))
    .setChoiceValues([
      bi('Student', 'Étudiant(e)'),
      bi('Trader or business owner', 'Commerçant(e) ou entrepreneur'),
      bi('Employee', 'Employé(e)'),
      bi('Other', 'Autre')])
    .setRequired(true);

  form.addScaleItem()
    .setTitle(bi('How comfortable are you with phones and the internet?',
                 'Êtes-vous à l’aise avec le téléphone et internet ?'))
    .setBounds(1, 5)
    .setLabels(bi('I need help', 'J’ai besoin d’aide'), bi('Very comfortable', 'Très à l’aise'))
    .setRequired(true);

  // 3. Your experience
  form.addPageBreakItem().setTitle(bi('Your experience with the chatbot', 'Votre expérience avec le chatbot'));

  form.addCheckboxItem()
    .setTitle(bi('Which languages did you use with the chatbot?', 'Quelles langues avez-vous utilisées avec le chatbot ?'))
    .setChoiceValues(['English', 'Français', 'Pidgin'])
    .setRequired(true);

  var langs = [['English', 'en anglais'], ['French', 'en français'], ['Pidgin', 'en pidgin']];
  langs.forEach(function (l) {
    form.addScaleItem()
      .setTitle(bi('How easy were the answers in ' + l[0] + ' to understand?',
                   'Les réponses ' + l[1] + ' étaient-elles faciles à comprendre ?'))
      .setHelpText(bi('Leave empty if you did not use this language.',
                      'Laissez vide si vous n’avez pas utilisé cette langue.'))
      .setBounds(1, 5)
      .setLabels(bi('Very hard', 'Très difficile'), bi('Very easy', 'Très facile'));
  });

  form.addScaleItem()
    .setTitle(bi('Did the answers give enough detail?', 'Les réponses donnaient-elles assez de détails ?'))
    .setBounds(1, 5)
    .setLabels(bi('Not enough', 'Pas assez'), bi('Plenty', 'Largement assez'))
    .setRequired(true);

  form.addScaleItem()
    .setTitle(bi('Overall, how do you rate CyberAware Cameroon?', 'Dans l’ensemble, comment notez-vous CyberAware Cameroon ?'))
    .setBounds(1, 5)
    .setLabels(bi('Poor', 'Mauvais'), bi('Excellent', 'Excellent'))
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle(bi('Which of these did you do?', 'Lesquelles de ces actions avez-vous faites ?'))
    .setChoiceValues([
      bi('Asked the chatbot a question', 'Posé une question au chatbot'),
      bi('Opened a free lesson', 'Ouvert une leçon gratuite'),
      bi('Did a lesson quiz', 'Fait le quiz d’une leçon'),
      bi('Tried to open a locked lesson', 'Essayé d’ouvrir une leçon verrouillée'),
      bi('I needed someone to help me', 'J’ai eu besoin de l’aide de quelqu’un')]);

  // 4. SUS
  form.addPageBreakItem()
    .setTitle(bi('How easy is it to use?', 'Facilité d’utilisation'))
    .setHelpText(bi('For each statement choose 1 (I strongly disagree) to 5 (I strongly agree).',
                    'Pour chaque phrase, choisissez de 1 (pas du tout d’accord) à 5 (tout à fait d’accord).'));

  var sus = [
    ['I think I would like to use this system often.', 'Je pense que j’aimerais utiliser ce système souvent.'],
    ['I found the system unnecessarily complex.', 'J’ai trouvé ce système inutilement complexe.'],
    ['I thought the system was easy to use.', 'J’ai trouvé ce système facile à utiliser.'],
    ['I think I would need the help of a technical person to use it.', 'Je pense que j’aurais besoin de l’aide d’une personne technique pour l’utiliser.'],
    ['I found the different functions well put together.', 'J’ai trouvé que les différentes fonctions étaient bien reliées.'],
    ['I thought there was too much inconsistency in the system.', 'J’ai trouvé qu’il y avait trop d’incohérences dans le système.'],
    ['I imagine most people would learn to use it very quickly.', 'J’imagine que la plupart des gens apprendraient très vite à l’utiliser.'],
    ['I found the system very awkward to use.', 'J’ai trouvé ce système très lourd à utiliser.'],
    ['I felt very confident using the system.', 'Je me suis senti(e) très en confiance en utilisant ce système.'],
    ['I needed to learn a lot of things before I could start.', 'J’ai dû apprendre beaucoup de choses avant de pouvoir commencer.']
  ];
  form.addGridItem()
    .setTitle(bi('Usability statements', 'Phrases sur l’utilisation'))
    .setRows(sus.map(function (s, i) { return (i + 1) + '. ' + bi(s[0], s[1]); }))
    .setColumns(['1', '2', '3', '4', '5'])
    .setRequired(true);

  // 5. Final questions
  form.addPageBreakItem().setTitle(bi('Last questions', 'Dernières questions'));

  form.addMultipleChoiceItem()
    .setTitle(bi('Would you use it again?', 'L’utiliseriez-vous encore ?'))
    .setChoiceValues([bi('Yes', 'Oui'), bi('Maybe', 'Peut-être'), bi('No', 'Non')])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle(bi('Would you pay 2,500 FCFA per month to unlock all 10 lessons?',
                 'Paieriez-vous 2 500 FCFA par mois pour débloquer les 10 leçons ?'))
    .setChoiceValues([bi('Yes', 'Oui'), bi('No', 'Non'), bi('Not sure', 'Pas sûr')])
    .setRequired(true);

  form.addParagraphTextItem().setTitle(bi('What did you like?', 'Qu’avez-vous aimé ?'));
  form.addParagraphTextItem().setTitle(bi('What should be improved?', 'Que faut-il améliorer ?'));

  // Answers go to a spreadsheet you can download as CSV.
  var sheet = SpreadsheetApp.create('CyberAware Cameroon - feedback answers');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  try { form.setPublished(true); } catch (e) { /* older Forms versions: already published */ }
  form.setAcceptingResponses(true);

  Logger.log('SEND THIS LINK to people : ' + form.getPublishedUrl());
  Logger.log('EDIT the form           : ' + form.getEditUrl());
  Logger.log('ANSWERS spreadsheet     : ' + sheet.getUrl());
}
