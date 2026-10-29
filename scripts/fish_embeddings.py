"""Pinned offline Chinese encoder; optional dependencies are imported only on explicit load."""
import hashlib
from pathlib import Path

MODEL_SHA='1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38'
TOKENIZER_SHA='48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26'
REVISION='46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59'
MODEL_IDENTITY={'repo':'Qdrant/bge-small-zh-v1.5','revision':REVISION,'weight_sha256':MODEL_SHA,'tokenizer_sha256':TOKENIZER_SHA,'dimension':512,'pooling':'normalized CLS','query_instruction':True}


def artifact_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb')as handle:
        while chunk:=handle.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()


class Encoder:
    def __init__(self,directory):
        directory=Path(directory);weight=directory/'model_optimized.onnx'
        if artifact_hash(weight)!=MODEL_SHA:raise ValueError('The local model does not match the pinned public weight.')
        if hashlib.sha256((directory/'tokenizer.json').read_bytes()).hexdigest()!=TOKENIZER_SHA:raise ValueError('The tokenizer does not match the pinned public model.')
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np=np
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.log_severity_level=3
        self.session=ort.InferenceSession(str(weight),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(directory/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=512);self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
        self.inputs={i.name for i in self.session.get_inputs()}

    def encode(self,texts,query=False):
        result=[]
        for start in range(0,len(texts),16):
            batch=texts[start:start+16]
            if query:batch=['为这个句子生成表示以用于检索相关文章：'+s for s in batch]
            encoded=self.tokenizer.encode_batch(batch)
            inputs={'input_ids':[e.ids for e in encoded],'attention_mask':[e.attention_mask for e in encoded],
                    'token_type_ids':[e.type_ids for e in encoded]}
            outputs=self.session.run(None,{k:self.np.asarray(v,dtype=self.np.int64)for k,v in inputs.items()if k in self.inputs})
            vectors=outputs[0][:,0,:]if outputs[0].ndim==3 else outputs[0]
            norms=self.np.linalg.norm(vectors,axis=1,keepdims=True)
            result.append(vectors/self.np.maximum(norms,1e-12))
        return self.np.concatenate(result)
