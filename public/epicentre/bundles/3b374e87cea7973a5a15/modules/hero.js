import {externalURL,ICONS} from './config.js';
import {icon} from './icons.js';

// Optional, independent of the carousel and YouTube state. Invalid drafts stay hidden.
export function heroSettings(value){
 if(value?.enabled!==true)return null;
 const label=typeof value.label==='string'?value.label.trim():'';
 const url=typeof value.url==='string'&&externalURL(value.url);
 if(!label||Array.from(label).length>40||/[\u0000-\u001f\u007f]/.test(label)||!url)return null;
 return{id:'hero-cta',label,url,icon:(ICONS.includes(value.icon)||value.icon==='cart')?value.icon:'external'};
}
export function installHeroCTA(config,root=document){
 const settings=heroSettings(config.heroCTA),panel=root.querySelector('#cta-zone');
 root.querySelector('#hero-cta')?.remove();
 root.querySelector('.installation')?.classList.toggle('has-hero-cta',!!settings);
 panel?.classList.toggle('has-hero-cta',!!settings);
 if(!settings||!panel)return null;
 const link=root.createElement('a');link.id='hero-cta';link.className='hero-cta';
 link.href=settings.url;link.target='_blank';link.rel='noopener noreferrer';
 link.title=settings.label+' (opens separately)';
 link.innerHTML=icon(settings.icon,'hero-primary')+'<span class="hero-label"></span><svg class="hero-external" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M7 6h11v11"/></svg>';
 link.querySelector('.hero-label').textContent=settings.label;
 link.setAttribute('aria-label',settings.label+' — opens in a new tab');
 link.addEventListener('click',()=>root.dispatchEvent(new CustomEvent('epicentre:hero-cta',{detail:{id:settings.id,machineId:config.machineId||null,destination:settings.url}})));
 panel.append(link);return link;
}
