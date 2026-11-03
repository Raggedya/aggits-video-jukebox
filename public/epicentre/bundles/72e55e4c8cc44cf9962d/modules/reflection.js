// This is a faint reflection of border light, never a duplicate of CTA content.
// The floor coordinates belong to the unchanged 1024x1536 lounge photograph.
export const FLOOR=Object.freeze({imageWidth:1024,imageHeight:1536,floorStartY:1254,inset:6,maxDepth:180,minDepth:32});

export function floorProjection(width,height,contentBottom){
 const scale=Math.max(width/FLOOR.imageWidth,height/FLOOR.imageHeight);
 const top=Math.max(FLOOR.floorStartY*scale+FLOOR.inset,contentBottom+FLOOR.inset);
 const depth=Math.min(FLOOR.maxDepth,height-top);
 return {top,depth,visible:depth>=FLOOR.minDepth};
}

export function createFloorReflection(root){
 const studio=root.closest('.studio'),surface=document.createElement('div'),plane=document.createElement('div'),lightTrack=document.createElement('div');
 surface.className='floor-reflection';surface.setAttribute('aria-hidden','true');surface.inert=true;plane.className='floor-reflection-plane';lightTrack.className='floor-reflection-track';plane.append(lightTrack);surface.append(plane);studio.append(surface);
 let position=0,rail=null,track=null,staticRow=false,geometry=null,disposed=false;
 // Called by the carousel's existing draw/scroll paths. No clock, RAF or layout read.
 function sync(value){position=value;lightTrack.style.transform=`translate3d(${-value}px,0,0)`;}
 function geometryChanged(){
  if(disposed||!rail||!track)return;
  const room=studio.getBoundingClientRect(),r=rail.getBoundingClientRect(),t=track.getBoundingClientRect(),installation=root.closest('.installation').getBoundingClientRect();
  const floor=studio.querySelector('.cabinet-floor')?.getBoundingClientRect();
  const projection=floor?{top:floor.top-room.top+FLOOR.inset,depth:Math.min(FLOOR.maxDepth,floor.height-FLOOR.inset),visible:floor.height-FLOOR.inset>=FLOOR.minDepth}:floorProjection(room.width,room.height,installation.bottom-room.top);
  const left=(staticRow?t.left:r.left)-room.left,width=staticRow?t.width:r.width;
  geometry={...projection,left,width};surface.hidden=!projection.visible||!lightTrack.childElementCount||root.hidden;
  surface.style.left=`${left}px`;surface.style.top=`${projection.top}px`;surface.style.width=`${width}px`;surface.style.height=`${Math.max(0,projection.depth)}px`;
 }
 function layout(sourceTrack,sourceRail,isStatic,value){
  track=sourceTrack;rail=sourceRail;staticRow=isStatic;
  const cards=track.querySelectorAll('.cta-card'),first=cards[0];lightTrack.replaceChildren();
  if(first){const size=first.getBoundingClientRect(),gap=getComputedStyle(track).columnGap;lightTrack.style.gap=gap;surface.style.setProperty('--reflection-card-width',`${size.width}px`);surface.style.setProperty('--reflection-card-height',`${size.height}px`);for(let i=0;i<cards.length;i++){const border=document.createElement('span');border.className='floor-reflection-border';lightTrack.append(border);}}
  sync(value);geometryChanged();
 }
 // Geometry is cached between builds/resizes. This observer has no animation loop.
 const resize=new ResizeObserver(geometryChanged);resize.observe(studio);const floor=studio.querySelector('.cabinet-floor');if(floor)resize.observe(floor);
 return {sync,layout,snapshot:()=>({position,transform:lightTrack.style.transform,borders:lightTrack.childElementCount,visible:!surface.hidden,geometry}),destroy(){disposed=true;resize.disconnect();surface.remove();}};
}
