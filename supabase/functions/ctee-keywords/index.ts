// CTEE-only keyword API. Data source: Supabase; no GitHub/Cloudflare sync.
// Browser access from the published CTEE GitHub Pages; all database writes stay server-side.
const ORIGIN = "https://hub-google.github.io";
const SUPABASE = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const ADMIN_PIN_HASH = Deno.env.get("CTEE_ADMIN_PIN_SHA256") ||
  "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7";
const CORS = {
  "Access-Control-Allow-Origin": ORIGIN,
  "Access-Control-Allow-Headers": "content-type, apikey, authorization",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Vary": "Origin",
  "Cache-Control": "no-store",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
};
const json = (value:unknown, status=200) =>
  new Response(JSON.stringify(value), {status,headers:CORS});
const toWord = (x:unknown):string => {
  if(typeof x!=="string") return "";
  const term=x.normalize("NFKC").trim();
  return term.length>=1 && term.length<=40 && !/[\r\n<>]/.test(term)?term:"";
};
const sha256 = async (value:string) => {
  const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest)).map(x=>x.toString(16).padStart(2,"0")).join("");
};
async function store(path:string, options:RequestInit={}):Promise<any> {
  const response=await fetch(SUPABASE+"/rest/v1/"+path,{
    ...options,
    headers:{
      "apikey":SERVICE_KEY,
      "Authorization":"Bearer "+SERVICE_KEY,
      "Content-Type":"application/json",
      ...(options.headers||{}),
    },
    cache:"no-store",
    signal:AbortSignal.timeout(15000),
  });
  const raw=await response.text();
  const body=raw?JSON.parse(raw):null;
  if(!response.ok){
    const message=typeof body?.message==="string"?body.message:"Database request failed";
    throw new Error(message.slice(0,180));
  }
  return body;
}
async function keywords(){
  const rows=await store("ctee_keywords?select=word&order=id.asc&limit=1000");
  if(!Array.isArray(rows)||!rows.length)throw new Error("目前沒有已啟用的關鍵字");
  return rows.map((row:any)=>row.word);
}
function sourceHash(request:Request){
  // Soft abuse-control signal only, never an authorization identity.
  return (request.headers.get("x-forwarded-for")||
    request.headers.get("cf-connecting-ip")||
    request.headers.get("x-real-ip")||
    "unknown").split(",")[0].trim().slice(0,80);
}
async function eventCount(ipHash:string,kind:string,minutes:number){
  const since=encodeURIComponent(new Date(Date.now()-minutes*60000).toISOString());
  const events=await store(
    "ctee_keyword_access_events?select=id&ip_hash=eq."+ipHash+
    "&event_type=eq."+kind+"&created_at=gte."+since+"&limit=7");
  return events.length;
}
async function logEvent(ipHash:string,kind:string){
  await store("ctee_keyword_access_events",{
    method:"POST",headers:{"Prefer":"return=minimal"},
    body:JSON.stringify({ip_hash:ipHash,event_type:kind})
  });
}
async function authorize(request:Request,pin:unknown){
  const ipHash=await sha256("ctee-admin|"+sourceHash(request));
  if(await eventCount(ipHash,"bad_pin",15)>=6){
    return {ok:false,error:"管理操作次數過多，請稍後再試",status:429};
  }
  if(typeof pin!=="string"||pin.length>80||await sha256(pin)!==ADMIN_PIN_HASH){
    await logEvent(ipHash,"bad_pin");
    return {ok:false,error:"管理金鑰錯誤",status:401};
  }
  return {ok:true};
}
async function handle(request:Request){
  if(request.method==="OPTIONS")return new Response(null,{status:204,headers:CORS});
  const origin=request.headers.get("Origin");
  if(origin&&origin!==ORIGIN)return json({ok:false,error:"來源不允許"},403);
  if(!SUPABASE||!SERVICE_KEY)return json({ok:false,error:"關鍵字服務尚未設定"},503);
  if(request.method==="GET")return json({ok:true,keywords:await keywords()});
  if(request.method!=="POST")return json({ok:false,error:"不支援此操作"},405);
  const raw=await request.text();
  if(raw.length>9000)return json({ok:false,error:"申請內容過長"},413);
  let data:any;
  try{data=JSON.parse(raw)}catch{return json({ok:false,error:"申請格式錯誤"},400)}
  if(!data||typeof data!=="object"||Array.isArray(data))return json({ok:false,error:"申請資料格式錯誤"},400);
  const action=data.action;
  if(action==="submit"){
    const requester=typeof data.name==="string"?data.name.normalize("NFKC").trim():"";
    const reason=typeof data.reason==="string"?data.reason.trim():"";
    const batchId=String(data.request_id||"");
    if(!requester||requester.length>40||/[\r\n<>]/.test(requester)||reason.length>500)
      return json({ok:false,error:"姓名或建議原因不符合格式"},400);
    if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(batchId))
      return json({ok:false,error:"申請編號錯誤"},400);
    if(!Array.isArray(data.items)||data.items.length<1||data.items.length>20)
      return json({ok:false,error:"一次需提出 1～20 個關鍵字"},400);
    const items=data.items.map((item:any)=>({
      operation:item?.operation==="add"?"add":item?.operation==="remove"?"remove":"",
      word:toWord(item?.keyword)
    }));
    if(items.some((item:any)=>!item.operation||!item.word)||
      new Set(items.map((item:any)=>item.operation+"|"+item.word)).size!==items.length)
      return json({ok:false,error:"關鍵字格式錯誤或重複"},400);
    const old=await store("ctee_keyword_requests?select=id&batch_id=eq."+batchId+"&limit=21");
    if(old.length)return json({ok:true,count:old.length,request_id:batchId,reused:true});
    const ipHash=await sha256("ctee-submit|"+sourceHash(request));
    if(await eventCount(ipHash,"submit",10)>=6)
      return json({ok:false,error:"送出過於頻繁，請稍後再試"},429);
    const payload=items.map((item:any,i:number)=>({
      batch_id:batchId,item_index:i,requester,reason,
      operation:item.operation,word:item.word
    }));
    await store("ctee_keyword_requests?on_conflict=batch_id,item_index",{
      method:"POST",
      headers:{"Prefer":"resolution=ignore-duplicates,return=representation"},
      body:JSON.stringify(payload)
    });
    await logEvent(ipHash,"submit");
    return json({ok:true,count:items.length,request_id:batchId},201);
  }
  if(action==="admin-list"||action==="review"){
    const authorization=await authorize(request,data.pin);
    if(!authorization.ok)return json({ok:false,error:authorization.error},authorization.status);
    if(action==="admin-list"){
      const items=await store("ctee_keyword_requests?select=id,batch_id,item_index,requester,reason,operation,word,status,created_at,reviewed_at&order=created_at.desc,item_index.asc&limit=1000");
      return json({ok:true,items,keywords:await keywords()});
    }
    const id=String(data.id||""),decision=data.decision;
    if(!/^[0-9a-f-]{36}$/i.test(id)||!["approved","rejected"].includes(decision))
      return json({ok:false,error:"審核資料格式錯誤"},400);
    let updated:any;
    try {
      updated=await store("rpc/ctee_review_keyword_item",{
        method:"POST",body:JSON.stringify({p_id:id,p_decision:decision}),
        headers:{"Prefer":"return=representation"}
      });
    }catch(error){
      const msg=String(error);
      if(msg.includes("Already reviewed"))return json({ok:false,error:"此項已審核，請重新整理"},409);
      if(msg.includes("Request not found"))return json({ok:false,error:"查無這筆申請"},404);
      if(msg.includes("Cannot remove last keyword"))
        return json({ok:false,error:"至少需要保留一個追蹤關鍵字，無法核准刪除最後一項"},409);
      throw error;
    }
    return json({ok:true,item:updated,keywords:await keywords(),synced:true});
  }
  return json({ok:false,error:"未知操作"},400);
}
Deno.serve(async (request:Request)=>{
  try {return await handle(request)}
  catch(error){
    console.error("ctee keywords error",error instanceof Error?error.name:"unknown");
    return json({ok:false,error:"服務暫時無法完成操作，請重新整理後再試"},503);
  }
});
