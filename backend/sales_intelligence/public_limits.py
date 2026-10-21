"""Shared public upload quota. Redis in production, bounded in-memory fallback locally."""
import hashlib
import hmac
import os
import time
from fastapi import HTTPException, Request

local_counts={}
SCRIPT="local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],70) end; return n"

async def public_limit(request: Request):
    now=int(time.time());window=now//60
    ip=request.client.host if request.client else 'unknown'
    if os.getenv('VERCEL')=='1':
        ip=request.headers.get('x-vercel-forwarded-for',ip).split(',')[0].strip()
    secret=os.getenv('SESSION_SECRET') or os.getenv('TELEGRAM_BOT_TOKEN') or 'local-development-only'
    ident=hmac.new(secret.encode(),ip.encode(),hashlib.sha256).hexdigest()[:24]
    keys=(f'si:web:{window}:ip:{ident}',f'si:web:{window}:global')
    if os.getenv('UPSTASH_REDIS_REST_URL') and os.getenv('UPSTASH_REDIS_REST_TOKEN'):
        from .webhook import Store
        try:
            store=Store()
            counts=[int(await store.command('EVAL',SCRIPT,1,key)) for key in keys]
        except Exception:
            raise HTTPException(503,'Защита загрузки временно недоступна. Попробуйте позже.') from None
    elif os.getenv('VERCEL')=='1':
        raise HTTPException(503,'Защита публичных загрузок не настроена.')
    else:
        for key in list(local_counts):
            if local_counts[key][0]!=window:del local_counts[key]
        if len(local_counts)>5000:raise HTTPException(429,'Слишком много запросов. Попробуйте через минуту.')
        counts=[]
        for key in keys:
            value=local_counts.get(key,(window,0))[1]+1
            local_counts[key]=(window,value);counts.append(value)
    if counts[0]>30 or counts[1]>300:
        raise HTTPException(429,'Слишком много загрузок или проверок. Повторите через минуту.',headers={'Retry-After':'60'})
