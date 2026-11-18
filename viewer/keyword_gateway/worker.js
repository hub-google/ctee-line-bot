/**
 * CTEE keyword inbox, isolated from the rest of the Cloudflare account.
 * The public browser never gets GitHub credentials.
 * This service only buffers anonymous submissions and per-item decisions.
 * GitHub Actions imports approved decisions into keywords.txt using GITHUB_TOKEN.
 */
const SITE_ORIGIN = "https://hub-google.github.io";
const MAX_ITEMS = 20;
const MAX_BODY = 8000;
const MAX_RECORDS = 600;

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": SITE_ORIGIN,
      "Access-Control-Allow-Headers": "Content-Type, X-CTEE-Admin-Pin",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Vary": "Origin",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    }
  });
}
function validTerm(input) {
  if (typeof input !== "string") return "";
  const x = input.normalize("NFKC").trim();
  return x && x.length <= 40 && !/[\r\n<>]/.test(x) ? x : "";
}
function cleanName(x) {
  if (typeof x !== "string") return "";
  const n = x.normalize("NFKC").trim();
  return n && n.length <= 40 && !/[\r\n<>]/.test(n) ? n : "";
}
async function digest(input) {
  const bytes = new TextEncoder().encode(input);
  const sum = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(sum)).map(b => b.toString(16).padStart(2,"0")).join("");
}
function safeSame(a, b) {
  // Constant-work comparison after SHA-256 digest.
  if (a.length !== b.length) return false;
  let x = 0;
  for (let i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return x === 0;
}
async function checkAdmin(request, env) {
  const pin = request.headers.get("X-CTEE-Admin-Pin") || "";
  if (!env.CTEE_ADMIN_PIN || pin.length > 100) return false;
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const hash = (await digest(ip + "|ctee-admin")).slice(0,32);
  const key = "admin-fail:" + hash;
  const fails = Number((await env.INBOX.get(key)) || 0);
  if (fails >= 6) return false;
  const a = await digest(pin);
  const b = await digest(env.CTEE_ADMIN_PIN);
  const correct = safeSame(a,b);
  if (!correct) await env.INBOX.put(key, String(fails + 1), { expirationTtl: 900 });
  return correct;
}
async function getRecords(env) {
  const records = [];
  let cursor;
  let loops = 0;
  do {
    const opts = { prefix: "request:", limit: 1000 };
    if (cursor) opts.cursor = cursor;
    const page = await env.INBOX.list(opts);
    const keys = page.keys || [];
    for (let i = 0; i < keys.length; i += 25) {
      const batch = await Promise.all(keys.slice(i, i+25).map(x => env.INBOX.get(x.name,"json")));
      for (const rec of batch) if (rec && rec.id && rec.keyword) records.push(rec);
      if (records.length >= MAX_RECORDS) break;
    }
    if (records.length >= MAX_RECORDS) break;
    cursor = page.list_complete ? "" : page.cursor;
    loops++;
  } while (cursor && loops < 10);
  return records.sort((a,b) => String(b.created_at).localeCompare(String(a.created_at)));
}
async function parseBody(request) {
  if (Number(request.headers.get("content-length") || "0") > MAX_BODY) throw Error("申請內容過長");
  const text = await request.text();
  if (text.length > MAX_BODY) throw Error("申請內容過長");
  const data = JSON.parse(text);
  if (!data || Array.isArray(data) || typeof data !== "object") throw Error("無效申請資料");
  return data;
}
export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null,{status:204,headers:{
      "Access-Control-Allow-Origin":SITE_ORIGIN,
      "Access-Control-Allow-Headers":"Content-Type, X-CTEE-Admin-Pin",
      "Access-Control-Allow-Methods":"GET, POST, OPTIONS",
      "Vary":"Origin"
    }});
    if (!env.INBOX) return response({error:"收件空間未完成設定"},503);
    const origin = request.headers.get("Origin");
    if (origin && origin !== SITE_ORIGIN) return response({error:"來源未授權"},403);
    const {pathname} = new URL(request.url);
    try {
      if (pathname === "/health" && request.method === "GET")
        return response({ok:true,service:"ctee-keyword-inbox",configured:!!env.CTEE_ADMIN_PIN});
      if (pathname === "/export" && request.method === "GET") {
        const items = await getRecords(env);
        return response({ok:true,items:items.filter(x=>x.status==="approved"||x.status==="rejected")
          .map(x=>({id:x.id,operation:x.operation,keyword:x.keyword,status:x.status,reviewed_at:x.reviewed_at}))});
      }
      if (pathname === "/reviews" && request.method === "GET") {
        if (!await checkAdmin(request,env)) return response({error:"管理金鑰不正確或暫時受限"},401);
        return response({ok:true,items:await getRecords(env)});
      }
      if (pathname === "/submit" && request.method === "POST") {
        const data = await parseBody(request);
        const name = cleanName(data.name);
        const reason = typeof data.reason==="string" ? data.reason.trim() : "";
        const requestId = String(data.request_id || "");
        if (!name || reason.length>500 || !/^[a-f0-9-]{36}$/.test(requestId))
          return response({error:"姓名或申請編號有誤"},400);
        if (!Array.isArray(data.items)||data.items.length<1||data.items.length>MAX_ITEMS)
          return response({error:"一次需提交 1～20 個關鍵字"},400);
        const items = data.items.map(x=>({
          operation: x && x.operation==="add" ? "add" : x && x.operation==="remove" ? "remove" : "",
          keyword: validTerm(x && x.keyword)
        }));
        if (items.some(x=>!x.operation||!x.keyword) || new Set(items.map(x=>x.operation+":"+x.keyword)).size!==items.length)
          return response({error:"關鍵字格式錯誤或重複"},400);
        const ip = request.headers.get("CF-Connecting-IP") || "unknown";
        const limitKey="submit-limit:"+(await digest(ip+"|ctee-submit")).slice(0,32);
        const count=Number(await env.INBOX.get(limitKey)||0);
        if(count>=6)return response({error:"申請過於頻繁，請稍後再試"},429);
        const now=new Date().toISOString();
        // Use deterministic names so a retry cannot create a fresh set of entries.
        for(let i=0;i<items.length;i++){
          const key="request:"+requestId+"-"+i;
          if(await env.INBOX.get(key))continue;
          await env.INBOX.put(key,JSON.stringify({
            id:requestId+"-"+i, request_id:requestId,
            name,reason,operation:items[i].operation,keyword:items[i].keyword,
            status:"pending",created_at:now,reviewed_at:null
          }));
        }
        await env.INBOX.put(limitKey,String(count+1),{expirationTtl:600});
        return response({ok:true,count:items.length,request_id:requestId},201);
      }
      if (pathname === "/review" && request.method === "POST") {
        if (!await checkAdmin(request,env)) return response({error:"管理金鑰不正確或暫時受限"},401);
        const data=await parseBody(request);
        if(typeof data.id!=="string"||!/^[a-f0-9-]{38,45}$/.test(data.id)||
           !["approved","rejected"].includes(data.decision))
          return response({error:"審核資料不合法"},400);
        const key="request:"+data.id;
        const current=await env.INBOX.get(key,"json");
        if(!current) return response({error:"查無申請"},404);
        if(current.status!== "pending") return response({error:"這項已審核，不能重複更改"},409);
        const updated={...current,status:data.decision,reviewed_at:new Date().toISOString()};
        await env.INBOX.put(key,JSON.stringify(updated));
        return response({ok:true,item:updated,notice:data.decision==="approved"?"已核准，等待 GitHub 排程寫入":"已駁回"});
      }
      return response({error:"無效路徑"},404);
    } catch(e) {
      console.error("CTEE keyword gateway",e instanceof Error?e.name:"unknown");
      if (e instanceof SyntaxError) return response({error:"資料格式不合法"},400);
      return response({error:"服務處理失敗，請稍後重試"},500);
    }
  }
};