export function initialiseShare(config={}){const button=document.querySelector('#share'),dialog=document.querySelector('#share-dialog'),field=document.querySelector('#share-url'),copy=document.querySelector('#copy-link'),status=document.querySelector('#copy-status'),notice=document.querySelector('#notice');let timer;

 const feedback=text=>{notice.textContent=text;clearTimeout(timer);timer=setTimeout(()=>notice.textContent='',4000);};

 button.addEventListener('click',async()=>{const url=new URL(config.shareURL||location.href);const privateDraft=document.body.dataset.preview==='true',local=config.publicationEnvironment!=='production';const title=config.machineTitle||'Epicentre — local prototype';const message=privateDraft?'Private draft preview — requires your Studio sign-in.':local?'Private preview — opens on the same Wi-Fi.':'Watch this video collection in Epicentre.';dialog.querySelector('p').textContent=message;url.search='';url.hash='';if(navigator.share){try{await navigator.share({title:local?'Epicentre — local prototype':title,text:message,url:url.href});feedback(local?'Share sheet closed. This preview requires the same Wi-Fi.':'Share sheet closed.');return;}catch(e){if(e.name==='AbortError'){feedback('Sharing cancelled.');return;}}}field.value=url.href;status.textContent='';dialog.showModal();});

 copy.addEventListener('click',async()=>{try{if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(field.value);else{field.focus();field.select();if(!document.execCommand('copy'))throw Error();}status.textContent=config.publicationEnvironment==='production'?'Public link copied.':'Preview link copied. Same Wi-Fi required.';}catch{field.focus();field.select();status.textContent=config.publicationEnvironment==='production'?'Select and copy this public link.':'Select and copy this preview link.';}});

}

