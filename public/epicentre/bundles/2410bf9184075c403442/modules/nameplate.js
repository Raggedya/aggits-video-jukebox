export function configuredMachineName(config){return typeof config?.machineTitle==='string'?config.machineTitle.trim():'';}
export function installNameplate(config,root=document){
 const title=root.querySelector('#video-title'),channel=root.querySelector('#creator-name'),frame=root.querySelector('.player-surround');
 if(!title||!channel||!frame)return;
 const existing=frame.querySelector('.video-nameplate'),plate=existing||root.createElement('div');
 if(!existing){plate.className='video-nameplate';const name=root.createElement('span');name.id='machine-name';plate.append(name);frame.append(plate);}
 const machine=configuredMachineName(config),name=plate.querySelector('#machine-name');
 name.textContent=machine;name.title=machine;name.setAttribute('aria-label',machine);plate.hidden=!machine;
 if(existing)return;
 const update=()=>{const full=title.textContent,credit=channel.textContent;title.title=full+(credit?' — '+credit:'');title.setAttribute('aria-label',full+(credit?' · '+credit:''));};
 update();const observer=new MutationObserver(update);
 for(const node of[title,channel])observer.observe(node,{childList:true,characterData:true,subtree:true});
 return()=>observer.disconnect();
}
