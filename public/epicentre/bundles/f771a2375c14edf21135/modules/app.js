import {createEngagement} from './engagement.js';
import {validateConfig} from './config.js';
import {createCarousel} from './carousel.js';
import {createJukebox} from './jukebox.js';
import {initialiseShare} from './share.js';
const problem=document.querySelector('#player-error');
function playerStatus(value,config){document.documentElement.dataset.playerState=value.state;document.dispatchEvent(new CustomEvent('splatters-video:playback',{detail:value}));problem.replaceChildren();problem.hidden=!value.error;if(value.error){problem.append(document.createTextNode(value.error+' '));const link=document.createElement('a');link.href=config.videoURL;link.textContent='Open on YouTube';link.target='_blank';link.rel='noopener noreferrer';problem.append(link);if(document.querySelector('#video-selector')){const skip=document.createElement('button');skip.type='button';skip.textContent='Try next video';skip.addEventListener('click',()=>window.dispatchEvent(new Event('splatters-video:skip-unavailable')));problem.append(document.createTextNode(' '),skip);}}}
try{
 const response=await fetch(document.body.dataset.configUrl||'demo.json',{cache:'no-store'});if(!response.ok)throw Error('The demonstration configuration could not be loaded.');const config=validateConfig(await response.json());document.querySelector('#video-title').textContent=config.title;document.querySelector('#creator-name').textContent=config.creator;document.title=config.creator+' — Epicentre';
 const carousel=createCarousel(document.querySelector('#cta-zone'),config.ctas);initialiseShare(config);createEngagement(config);let jukebox;window.addEventListener('splatters-video:skip-unavailable',()=>jukebox?.next());const events=[];document.addEventListener('splatters-video:playback',event=>{events.push({...event.detail,at:performance.now()});if(events.length>40)events.shift();});
 // Read-only diagnostics for this local prototype. No provider state is simulated.
 if(new URLSearchParams(location.search).has('debug'))Object.defineProperty(window,'__SPLATTERS_VIDEO__',{value:Object.freeze({snapshot:()=>({applicationId:'splatters-video',mode:'local-prototype',player:jukebox?.playerSnapshot()||null,selector:jukebox?.snapshot()||null,carousel:carousel.snapshot(),events:[...events],analyticsEnabled:false,publishingEnabled:false})})});
 jukebox=createJukebox(config,(status,video)=>playerStatus(status,video));
}catch(error){problem.textContent=error.message;problem.hidden=false;}
