import{mechanicalCadence}from'./machine-mechanics-core.js';

export const ARTIST_SINGLE_REEL_PROFILE=Object.freeze({
  duration:2350,
  reducedMotionDuration:620,
  lockClassDuration:260,
});

export function populateSingleReel({reel,entry,pickRandom,labelFor,identityFor,setLabel,neighbours=true}){
  const strip=reel.querySelector('.reel-strip');
  if(!strip||strip.children.length!==3)throw new Error('single_reel_requires_three_slots');
  const current=labelFor(entry),used=new Set([identityFor(entry)]);
  const pickNeighbour=()=>{
    const item=pickRandom(used);
    if(item)used.add(identityFor(item));
    return labelFor(item||entry);
  };
  const before=neighbours?pickNeighbour():current;
  const after=neighbours?pickNeighbour():current;
  [before,current,after].forEach((label,row)=>setLabel(strip.children[row],label));
}

export function spinSingleReel({
  reel,
  finalEntry,
  stopAfter=ARTIST_SINGLE_REEL_PROFILE.duration,
  pickRandom,
  renderRows,
  reelIndex=0,
  onStop=()=>{},
  onProgress=()=>{},
  now=()=>performance.now(),
  requestFrame=callback=>requestAnimationFrame(callback),
}){
  const strip=reel.querySelector('.reel-strip');
  reel.classList.add('is-spinning');
  const started=now();
  let lastSwap=0;
  let current=pickRandom();
  return new Promise(resolve=>{
    const tick=frameTime=>{
      const elapsed=frameTime-started,progress=Math.min(1,elapsed/stopAfter);
      onProgress(progress);
      const cadence=mechanicalCadence(progress,reelIndex);
      const rowHeight=Math.max(16,reel.clientHeight/3),phase=((frameTime-lastSwap)/cadence)%1;
      strip.style.transform=`translate3d(0,${((phase-.5)*rowHeight).toFixed(2)}px,0)`;
      if(frameTime-lastSwap>cadence){current=pickRandom();renderRows(current);lastSwap=frameTime}
      if(elapsed>=stopAfter){
        strip.style.transform='';renderRows(finalEntry);reel.classList.remove('is-spinning');reel.classList.add('is-locking');
        setTimeout(()=>reel.classList.remove('is-locking'),ARTIST_SINGLE_REEL_PROFILE.lockClassDuration);
        onStop(reelIndex);resolve();return;
      }
      requestFrame(tick);
    };
    requestFrame(tick);
  });
}
