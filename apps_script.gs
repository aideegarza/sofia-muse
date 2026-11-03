// Google Apps Script web app: receives one processed call and writes it to the sheet.
// Paste this in the sheet: Extensions > Apps Script. Set TOKEN to the same value as
// SHEETS_TOKEN on the server. Deploy > New deployment > Web app,
// Execute as: Me, Who has access: Anyone.

const TOKEN = 'CAMBIA-ESTE-TOKEN';
const SHEET_NAME = 'Llamadas';

function doPost(e) {
  const body = JSON.parse(e.postData.contents);
  if (body.token !== TOKEN) return json_({ ok: false, error: 'bad token' });

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
    const columns = body.columns;

    if (sheet.getLastRow() === 0) {
      sheet.appendRow(['processed_at'].concat(columns));
      sheet.setFrozenRows(1);
    }
    const header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const values = header.map(function (col) {
      if (col === 'processed_at') return new Date();
      const v = body.row[col];
      return v === null || v === undefined ? '' : v;
    });

    // Upsert by call_id so webhook retries never duplicate a row.
    const idCol = header.indexOf('call_id') + 1;
    const last = sheet.getLastRow();
    let target = 0;
    if (idCol > 0 && last > 1) {
      const ids = sheet.getRange(2, idCol, last - 1, 1).getValues();
      for (let i = 0; i < ids.length; i++) {
        if (ids[i][0] === body.row.call_id) { target = i + 2; break; }
      }
    }
    if (target) sheet.getRange(target, 1, 1, values.length).setValues([values]);
    else sheet.appendRow(values);

    return json_({ ok: true, row: target || sheet.getLastRow() });
  } finally {
    lock.releaseLock();
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
