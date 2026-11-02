// Stable, independent seeds avoid arranging snow into diagonal dotted lines.
export function weatherParticles(count=72) {
  let state=0x39ab68f1;
  const random=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;return(state>>>0)/4294967296;};
  return Array.from({length:count},()=>({x:random(),phase:random(),drift:random()*Math.PI*2,speed:random()}));
}
export function precipitationPosition(particle,time,weather) {
  const snow=weather==='snow', speed=snow ? .13+particle.speed*.14 : .8+particle.speed*.25;
  return {
    x:-.91+particle.x*3.23+(snow?Math.sin(time*.6+particle.drift)*.055:0),
    y:.98+((particle.phase*1.99-time*speed)%1.99+1.99)%1.99,
    z:-3.1,
  };
}
