#!/usr/bin/env python3
"""One local embedding request. No retrieval, database access, network or automatic installation."""
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fish_embedding_process import PROTOCOL,MODEL_KEY,MAX_INPUT
from fish_embeddings import Encoder


def main():
    request_id=''
    try:
        if len(sys.argv)!=2:raise ValueError('Model directory required.')
        raw=sys.stdin.buffer.read(MAX_INPUT+1)
        if len(raw)>MAX_INPUT:raise ValueError('Request too large.')
        request=json.loads(raw)
        if not isinstance(request,dict)or set(request)!={'protocol','id','query','texts'}or type(request['protocol'])is not int or request['protocol']!=PROTOCOL or not isinstance(request['id'],str)or not re.fullmatch('[a-f0-9]{32}',request['id'])or type(request['query'])is not bool:raise ValueError('Invalid protocol.')
        texts=request['texts'];request_id=request['id']
        if not isinstance(texts,list)or not 1<=len(texts)<=16 or any(not isinstance(s,str)or not 1<=len(s)<=2000 for s in texts):raise ValueError('Invalid texts.')
        vectors=Encoder(Path(sys.argv[1])).encode(texts,query=request['query']).tolist()
        print(json.dumps({'protocol':PROTOCOL,'id':request_id,'model':MODEL_KEY,'vectors':vectors},separators=(',',':'),allow_nan=False))
    except Exception:
        print(json.dumps({'protocol':PROTOCOL,'id':request_id,'error':'encoder_unavailable'}));return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
