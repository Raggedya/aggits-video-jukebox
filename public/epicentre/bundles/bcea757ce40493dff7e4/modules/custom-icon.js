export const CUSTOM_LIMIT=4096;
export function customShape(value){
 if(!value||typeof value.name!=='string'||value.name.length>60||/[\x00-\x1f<>]/.test(value.name)||typeof value.data!=='string'||!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value.data)||value.data.length>22+Math.ceil(CUSTOM_LIMIT/3)*4)return null;
 try{const bytes=Uint8Array.from(atob(value.data.slice(22)),c=>c.charCodeAt(0));if(bytes.length>CUSTOM_LIMIT||bytes.length<45||[137,80,78,71,13,10,26,10].some((v,i)=>v!==bytes[i]))return null;const d=new DataView(bytes.buffer),width=d.getUint32(16),height=d.getUint32(20);if(!width||!height||width>128||height>128)return null;return{name:value.name.trim()||'Custom icon',data:value.data};}catch{return null;}
}
