export function roomEnvironment(period = 'auto', weather = 'clear', now = new Date()) {
  const hour = Number(new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai', hour:'2-digit', hourCycle:'h23'}).format(now));
  const resolved = ['day','dusk','night'].includes(period) ? period : hour >= 7 && hour < 17 ? 'day' : hour >= 17 && hour < 19 ? 'dusk' : 'night';
  const palette = {
    day: {label:'日光慢慢', background:'#eef3f2', sky:'#b5dce5', ambient:2.1, sun:3.2, lamp:0.65},
    dusk: {label:'黄昏小憩', background:'#f3e8e3', sky:'#eabca8', ambient:1.35, sun:2.4, lamp:1.6},
    night: {label:'留一盏灯', background:'#e4e9f1', sky:'#354d70', ambient:0.65, sun:0.55, lamp:3.1},
  }[resolved];
  const safeWeather = ['clear','rain','snow'].includes(weather) ? weather : 'clear';
  return {...palette, period:resolved, weather:safeWeather, ambient:palette.ambient * (safeWeather === 'rain' ? .82 : 1)};
}

// Presentation follows the existing activity service; idle is not evidence of reading or sleep.
export function roomActivity(state) {
  const animation = {surfing:'working', working:'working', thinking:'thinking', offline:'look'}[state?.state] || 'idle';
  return {animation, label:typeof state?.label === 'string' ? state.label : '在小屋里待着呢'};
}

export function roomFrustum(aspect, corners) {
  const xs=corners.map(p=>p.x), ys=corners.map(p=>p.y);
  const left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys);
  const height=Math.max(top-bottom+.9,(right-left+.9)/aspect), width=height*aspect;
  const cx=(left+right)/2,cy=(bottom+top)/2;
  return {left:cx-width/2,right:cx+width/2,top:cy+height/2,bottom:cy-height/2};
}
