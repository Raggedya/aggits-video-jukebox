import {icon as legacyIcon}from './legacy-icons.js';
import {CATALOGUE}from './icon-catalogue.js';
import {ASSETS}from './icon-assets.js';
import {customShape}from './custom-icon.js';
export function icon(key,unique='',custom){
 const entry=CATALOGUE.find(i=>i.id===key);
 if(entry?.style==='legacy'||!entry&&key!=='custom')return legacyIcon(key,unique);
 const image=key==='custom'?customShape(custom)?.data:ASSETS[entry?.asset];
 if(!image)return legacyIcon('external',unique);
 const content=image.startsWith('data:')?'<image href="'+image+'" x="0" y="0" width="24" height="24" preserveAspectRatio="xMidYMid meet"/>':image;
 return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'+content+'</svg>';
}
