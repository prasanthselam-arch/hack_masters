/**
 * Health Copilot mail relay: sends the app's emails (sign-up codes, password resets, alerts) from your Gmail.
 *
 * Setup (see "Email" in the README):
 *   1. https://script.google.com -> New project -> replace the code with this file -> Save.
 *   2. Project Settings (gear) -> Script properties -> add SECRET = the GOOGLE_SCRIPT_SECRET value from Render.
 *   3. Deploy -> New deployment -> type "Web app", Execute as "Me", Who has access "Anyone" -> Deploy,
 *      allow the Gmail permission, and copy the Web app URL into GOOGLE_SCRIPT_URL on Render.
 *
 * Gmail accounts can send about 100 emails a day this way. Requests without the right secret are ignored.
 */

function doPost(e) {
  var secret = PropertiesService.getScriptProperties().getProperty('SECRET');
  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply({ ok: false, error: 'bad request' });
  }
  if (!secret || body.secret !== secret) return reply({ ok: false, error: 'forbidden' });
  if (!body.to || !body.subject) return reply({ ok: false, error: 'missing recipient or subject' });
  if (MailApp.getRemainingDailyQuota() < 1) return reply({ ok: false, error: 'daily Gmail quota used up' });

  MailApp.sendEmail({
    to: body.to,
    subject: body.subject,
    body: body.text || '',
    htmlBody: body.html || undefined,
    name: body.name || 'Health Copilot',
  });
  return reply({ ok: true, remaining: MailApp.getRemainingDailyQuota() });
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
