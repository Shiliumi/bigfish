export interface WeatherParticle {x:number;phase:number;drift:number;speed:number}
export function weatherParticles(count?:number):WeatherParticle[];
export function precipitationPosition(particle:WeatherParticle,time:number,weather:string):{x:number;y:number;z:number};
