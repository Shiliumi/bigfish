// Activity follows real work. No sentiment inference or additional model requests.
export function companionState({ connected = true, activities = [], jobs = [], unread = 0, outingStarted = false } = {}) {
  if (!connected) return { animation: 'idle', label: '鱼塘暂时离线', state: 'offline', unread };
  if (activities.length) {
    const surfing = activities.includes('surfing'), working = activities.includes('working');
    return { animation: surfing || working ? 'working' : 'thinking', label: surfing ? '正在翻网页' : working ? '正在动手处理' : '正在想怎么回你', state: surfing ? 'surfing' : working ? 'working' : 'thinking', unread };
  }
  if (jobs.some(j => j.name === 'fish-surf' && j.latest_execution?.status === 'running')) return outingStarted ? { animation: 'working', label: '正追着感兴趣的东西逛', state: 'surfing', unread } : { animation: 'thinking', label: '在想今天还惦记什么', state: 'thinking', unread };
  return { animation: unread ? 'greeting' : 'idle', label: unread ? '给你带了新发现' : '在鱼塘待着呢', state: unread ? 'letter' : 'idle', unread };
}
