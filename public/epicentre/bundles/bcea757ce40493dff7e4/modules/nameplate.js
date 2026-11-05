export function configuredMachineName(config){return typeof config?.machineTitle==='string'?config.machineTitle.trim():'';}
export function installNameplate(config,root=document){
 const title=root.querySelector('#video-title'),channel=root.querySelector('#creator-name'),frame=root.querySelector('.player-surround'),header=root.querySelector('.masthead');if(!title||!channel||!frame||!header)return;
 const heading=root.createElement('section');heading.className='machine-heading';heading.setAttribute('aria-label','Machine identity');
 const name=root.createElement('h1');name.id='machine-name';name.className='machine-title';name.textContent=configuredMachineName(config);name.title=name.textContent;
 const subtitle=root.createElement('p');subtitle.className='machine-subtitle';subtitle.hidden=!config.machineSubtitle;const text=root.createElement('span');text.textContent=config.machineSubtitle||'';subtitle.append(text);heading.append(name,subtitle);heading.hidden=!name.textContent;header.after(heading);
 const plate=root.createElement('div');plate.className='video-nameplate';const identification=root.createElement('span');identification.id='video-identification';plate.append(identification);frame.append(plate);
 const update=()=>{const full=title.textContent;identification.textContent=full;identification.title=full;identification.setAttribute('aria-label',full);};update();const observer=new MutationObserver(update);observer.observe(title,{childList:true,characterData:true,subtree:true});
 // Fit whole words within at most three lines; never alter the configured name.
 const fit=()=>{name.style.fontSize='';const css=getComputedStyle(name),preferred=parseFloat(css.fontSize),width=name.clientWidth;const canvas=root.createElement('canvas'),ctx=canvas.getContext('2d'),words=name.textContent.toUpperCase().split(/\s+/);for(let size=preferred;size>=1;size-=.5){name.style.fontSize=size+'px';ctx.font=`700 ${size}px ${css.fontFamily}`;if(words.every(w=>ctx.measureText(w).width+Math.max(0,w.length-1)*parseFloat(css.letterSpacing||0)<=width)&&name.scrollWidth<=width+1&&name.scrollHeight<=size*1.08*3+2)break;}};
 const resize=new ResizeObserver(fit);resize.observe(heading);root.fonts?.ready.then(fit);fit();return()=>{observer.disconnect();resize.disconnect();};
}
