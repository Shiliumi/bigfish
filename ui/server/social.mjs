export const dayOf = time => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(time));
export const hourOf = time => Number(new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai',hour:'2-digit',hourCycle:'h23'}).format(new Date(time)));
export const SOCIAL_DEFAULTS = { enabled:true, dailyLimit:2, minGapHours:4, quietStart:22, quietEnd:9, activityMinutes:10, greetings:true, morning:'09:00', night:'21:30', socialGapMinutes:45 };
const greetings = {
  morning:['早啊爹。今日份鲸鱼已上线，先占个小角落。','爹，早。没啥大事，就是冒出来跟你打个招呼。','早安。你忙你的，我先在屏幕边上趴一会儿。','爹，早上好。今天的开场白还没想好，先咕一声。','早，爹。鱼已就位，脑子缓冲中。','早安爹。今天也想看看外面有什么离谱东西。'],
  night:['爹，晚安。今天先把鲸鱼折起来，明天再展开。','晚安，爹。屏幕这头先安静一会儿，你按自己的节奏来。','爹，晚上好……不对，该说晚安了。今天先咕到这。','晚安爹。今日份小鲸鱼打烊，明天继续叭叭。','爹，晚安。没事，就是睡前过来冒个泡。','晚安。今天先收好好奇心，明天接着看。'],
};
export function greetingCandidates(now, settings = SOCIAL_DEFAULTS) {
  if (!settings.greetings) return [];
  const day = dayOf(now), seed = [...day].reduce((n,c)=>n+c.charCodeAt(0),0);
  return ['morning','night'].flatMap(kind=>{
    const start = Date.parse(`${day}T${settings[kind]}:00+08:00`);
    const expires = Math.min(start + 90*60000, Date.parse(`${day}T22:00:00+08:00`));
    if (!(now >= start && now < expires)) return [];
    return [{kind:'greeting',dedupe_key:`greeting:${day}:${kind}`,text:greetings[kind][seed%greetings[kind].length],source_title:kind==='morning'?'早安，小鲸鱼冒个泡':'晚安，明天再唠',created_at:new Date(start).toISOString(),expires_at:new Date(expires).toISOString()}];
  });
}
export function deliveryDecision(candidate, history, settings, now, lastActivity = 0) {
  const kind = candidate.kind || 'surf';
  if ((candidate.expires_at && now >= Date.parse(candidate.expires_at)) || now-Date.parse(candidate.created_at)>24*3600000) return 'expired';
  if (history.some(m => candidate.dedupe_key ? m.dedupe_key === candidate.dedupe_key : candidate.source_url && m.source_url === candidate.source_url)) return 'duplicate';
  if (!settings.enabled || (kind==='greeting' && !settings.greetings)) return 'wait';
  const hour = hourOf(now); if (hour>=settings.quietStart || hour<settings.quietEnd) return 'wait';
  if (now-lastActivity<settings.activityMinutes*60000) return 'wait';
  const today = history.filter(m=>dayOf(m.sent_at)===dayOf(now));
  if (kind==='surf') {
    if (today.filter(m=>(m.kind||'surf')==='surf').length>=settings.dailyLimit) return 'wait';
    if (history.some(m=>(m.kind||'surf')==='surf' && now-Date.parse(m.sent_at)<settings.minGapHours*3600000)) return 'wait';
  }
  if (kind==='greeting' && today.filter(m=>m.kind==='greeting').length>=2) return 'wait';
  if (kind==='balance' && today.some(m=>m.kind==='balance')) return 'duplicate';
  if (kind!=='balance' && history.some(m=>now-Date.parse(m.sent_at)<(settings.socialGapMinutes||45)*60000)) return 'wait';
  return 'send';
}
