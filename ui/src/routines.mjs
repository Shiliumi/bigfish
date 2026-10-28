export function routineInfo(job){
 if(job.name==='fish-surf')return {title:'出去看看世界',description:'追着感兴趣的问题去找作品和讨论，没想看的就歇会儿。',kind:'surf',actionName:'自主冲浪',scheduleCaption:'出发机会'};
 if(job.name==='fish-memory')return {title:'给记忆做个整理',description:'翻翻新经历，把值得记住的事留下来。',kind:'memory',actionName:'记忆整理',scheduleCaption:'执行时间'};
 const title=typeof job.name==='string'&&job.name.trim()?job.name:'自定义日常';
 return {title,description:'按你设置的时间执行这项任务，可查看具体执行记录。',kind:'custom',actionName:title,scheduleCaption:'执行时间'};
}
