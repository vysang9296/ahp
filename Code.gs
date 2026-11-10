// Google Sheet > 확장 프로그램 > Apps Script 에 붙여넣고, 배포 > 새 배포 > 웹 앱
// (실행: 나, 액세스: 모든 사용자) 로 배포한 뒤 URL을 HTML의 WEBAPP_URL과 Agent 스크립트에 넣는다.
// 요인 이름은 응답에 담겨 오므로 요인을 바꿔도 이 파일은 고칠 필요가 없다. 요인을 바꾸면 새 탭에 쌓인다.
function doPost(e) {
  const p = JSON.parse(e.postData.contents);
  const C = p.criteria;
  const ss = SpreadsheetApp.getActive();
  const name = "responses_" + C.join("/").slice(0, 60).replace(/[\[\]\*\?:\\\/]/g, "_");
  const sh = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sh.getLastRow() === 0) {
    sh.appendRow(["timestamp","source","respondent_id","role","model","run","CR","CR_처음"]
      .concat(C.map(c => "w_" + c), C.map(c => "A점수_" + c), ["종합_A(PFA기준)","종합_B(PFA기준)","종합_A_단순비례","종합_B_단순비례","attempts","CR통과","raw_json"]));
  }
  sh.appendRow([p.timestamp, p.source, p.respondent_id, p.role, p.model, p.run, p.cr, p.cr_initial===undefined ? p.cr : p.cr_initial]
    .concat(p.weights, p.alt_local.map(a => a[0]), [p.total[0], p.total[1], (p.total_simple||[""])[0], (p.total_simple||["",""])[1], p.attempts||1, p.cr_pass===undefined ? (p.cr<0.1) : p.cr_pass, JSON.stringify(p.raw)]));
  return ContentService.createTextOutput("ok");
}
