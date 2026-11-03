import {roomEnvironment} from './environment.mjs';
import {objects,surfaces} from './layout.mjs';

// These IDs are also required by scene.group(), so the inspection inventory cannot omit
// a rendered furniture group merely because it is fixed rather than movable.
export const roomItems={
  bed:{name:'床',area:'房间左边',details:'铺着蓝色被子、枕头，床上有蓝色鲸鱼玩偶'},
  lamp:{name:'床头柜和台灯',area:'床和书桌之间',details:'两层抽屉的小柜子，上面有台灯'},
  desk:{name:'书桌和电脑',area:'海景窗前',details:'木色书桌、抽屉、显示器和键盘，屏幕是装饰海景'},
  chair:{name:'椅子',area:'书桌前',details:'蓝绿色带轮椅子'},
  shelf:{name:'书架',area:'左侧靠墙',details:'书架上放着多本书，和可移动的小本子不是同一件物品'},
  window:{name:'海景窗和窗台',area:'房间后墙',details:'有窗帘，可以看到虚拟海景和所选雨雪氛围'},
  plant:{name:'盆栽',area:'书桌右前方',details:'白色花盆里的绿植；左墙高处的搁板还放着小盆栽'},
  picture:{name:'装饰画',area:'左墙',details:'木框海色小画，旁边有搁板'},
  rug:{name:'鲸鱼地毯',area:'房间中央',details:'浅蓝色圆地毯，是她散步时会经过的地方'},
  cup:{name:'杯子'},book:{name:'小本子'},cushion:{name:'蓝色抱枕'},
};
export function validateAtmosphere(value){
  if(!value||Object.keys(value).sort().join()!=='lamp,period,weather'||!['auto','day','dusk','night'].includes(value.period)||!['clear','rain','snow'].includes(value.weather)||typeof value.lamp!=='boolean')throw Error('房间氛围格式不正确。');
  return {period:value.period,weather:value.weather,lamp:value.lamp};
}
export function describeRoom(snapshot,now=new Date()){
  const preferences=snapshot.environment||{period:'auto',weather:'clear',lamp:true},env=roomEnvironment(preferences.period,preferences.weather,now);
  return {name:'大肥鱼的小屋',ownership:'这是大肥鱼在应用里的虚拟房间，和用户正在看的三维小屋是同一个场景。',
    representation:'角色在房间路线间活动，可坐在电脑前或到床上休息。这是虚拟空间的位置，不代表现实身体，也不据此推断用户所在位置或后台工作。',
    revision:snapshot.revision,observed_at:now.toISOString(),layout_state:'已保存的房间布置；未保存的拖动草稿不会覆盖这份状态。',
    environment:{period:env.period,weather:env.weather,lamp:preferences.lamp,source:snapshot.environment?'saved_scene':'default_scene',note:'时段、海景与雨雪是房间画面氛围，不是用户当地的真实天气。'},
    fixed_furnishings:Object.entries(roomItems).filter(([id])=>!Object.hasOwn(objects,id)).map(([id,item])=>({id,...item,movable:false})),
    movable_items:Object.entries(objects).map(([id,item])=>({id,name:item.label,at:surfaces[snapshot.layout[id].surface].label,locked:snapshot.locks[id],allowed_places:item.surfaces.map(surface=>({id:surface,name:surfaces[surface].label}))})),
    scope:'可移动物品只有杯子、小本子、抱枕；这不是房间全部家具清单。固定物品真实显示在画面里，只是暂不支持搬动。',
    capabilities:{move:true,photo:true,photo_method:'从三维小屋渲染全景或窗边画面，不需要现实摄像头；只能依据新的拍照成功回执发图。'},
    recent_actions:snapshot.actions.slice(0,3)};
}
