export const MUSIC_MACHINE_REEL_PROFILE=Object.freeze({
  accelerationEnd:.18,
  cruiseEnd:.7,
  minimumCadence:44,
  launchCadence:124,
  decelerationRange:190,
  leverResistanceExponent:.78,
  leverTrigger:.72,
  leverAngle:11,
});

const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

export function mechanicalCadence(progress,reelIndex=0){
  const value=clamp(progress,0,1),profile=MUSIC_MACHINE_REEL_PROFILE;
  if(value<profile.accelerationEnd)return profile.launchCadence-(value/profile.accelerationEnd)*(profile.launchCadence-profile.minimumCadence);
  if(value<profile.cruiseEnd)return profile.minimumCadence+reelIndex*2;
  return profile.minimumCadence+Math.pow((value-profile.cruiseEnd)/(1-profile.cruiseEnd),2)*profile.decelerationRange;
}

export function mechanicalReelProgress(progress){
  const value=clamp(progress,0,1);
  if(value<.18)return .12*Math.pow(value/.18,2);
  if(value<.7)return .12+.48*((value-.18)/.52);
  if(value<.94)return .6+.403*(1-Math.pow(1-(value-.7)/.24,3));
  return 1.003-.003*(-(Math.cos(Math.PI*((value-.94)/.06))-1)/2);
}

export function leverResistance(progress){
  return Math.pow(clamp(progress,0,1),MUSIC_MACHINE_REEL_PROFILE.leverResistanceExponent);
}
