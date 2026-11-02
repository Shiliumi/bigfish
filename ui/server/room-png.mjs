import {inflateSync} from 'node:zlib';
const signature=Buffer.from([137,80,78,71,13,10,26,10]);
export const MAX_PHOTO_BYTES=2*1024*1024;
const crcTable=Array.from({length:256},(_,n)=>{for(let i=0;i<8;i++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
export function crc32(bytes){let n=0xffffffff;for(const b of bytes)n=crcTable[(n^b)&255]^(n>>>8);return(n^0xffffffff)>>>0;}
export function validatePhoto(data){
  if(typeof data!=='string'||!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(data)||data.length>MAX_PHOTO_BYTES*4/3+64)throw Error('照片格式或大小不正确。');
  const bytes=Buffer.from(data.slice(22),'base64');if(bytes.length>MAX_PHOTO_BYTES||!bytes.subarray(0,8).equals(signature))throw Error('照片不是有效的 PNG。');
  let offset=8,width=0,height=0,channels=0,ended=false,count=0;const keep=[signature],compressed=[];
  while(offset<bytes.length){
    if(++count>256||offset+12>bytes.length)throw Error('照片数据不完整。');
    const length=bytes.readUInt32BE(offset),end=offset+12+length;if(end>bytes.length)throw Error('照片数据不完整。');
    const type=bytes.toString('ascii',offset+4,offset+8),payload=bytes.subarray(offset+8,end-4);
    if(crc32(bytes.subarray(offset+4,end-4))!==bytes.readUInt32BE(end-4))throw Error('照片校验失败。');
    if(count===1&&type!=='IHDR')throw Error('照片缺少尺寸。');
    if(type==='IHDR'){
      if(count!==1||length!==13)throw Error('照片尺寸格式不正确。');width=payload.readUInt32BE(0);height=payload.readUInt32BE(4);channels=payload[9]===6?4:payload[9]===2?3:0;
      if(width<1||height<1||width>1280||height>1280||!channels||payload[8]!==8||payload[10]||payload[11]||payload[12])throw Error('照片尺寸或编码不支持。');
      keep.push(bytes.subarray(offset,end));
    }else if(type==='IDAT'){if(!width)throw Error('照片缺少尺寸。');compressed.push(payload);keep.push(bytes.subarray(offset,end));}
    else if(type==='IEND'){if(length||end!==bytes.length||!compressed.length)throw Error('照片结束标记不正确。');keep.push(bytes.subarray(offset,end));ended=true;}
    else if(type[0]===type[0].toUpperCase())throw Error('照片包含不支持的编码。');
    offset=end;
  }
  if(!ended)throw Error('照片数据不完整。');
  const stride=width*channels+1,decoded=inflateSync(Buffer.concat(compressed),{maxOutputLength:stride*height});
  if(decoded.length!==stride*height)throw Error('照片像素数量不正确。');
  for(let y=0;y<height;y++)if(decoded[y*stride]>4)throw Error('照片像素格式不正确。');
  return {bytes:Buffer.concat(keep),width,height};
}
