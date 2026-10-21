import pytest

@pytest.fixture
def csv_data():
    # Synthetic fixture with the same analytical structure as the assignment.
    return """дата,имя,телефон,источник,бюджет
19.10.2026,Тест А,+70000000001,Яндекс,12000000
2026-10-19,Тест А,80000000001,yandex,12000000
18.10.2026,Тест Б,+70000000002,Авито,0
18.10.2026,Тест В,+70000000003,Я.Директ,
17.10.2026,Тест Г,+70000000004,сайт,8500000
2026-10-17,Тест Д,+70000000005,Авито,
16.10.2026,Тест Е,+70000000006,сарафан,9000000
19.10.2026,Тест Б,+70000000002,Авито,0
""".encode()

@pytest.fixture
def anyio_backend():
    return 'asyncio'

class MemoryStore:
    """Redis test double with NX and real TTL semantics under a controlled clock."""
    def __init__(self): self.data={};self.expiry={};self.now=0
    async def command(self,*args):
        op,key,*tail=args
        if self.expiry.get(key,float('inf')) <= self.now:
            self.data.pop(key,None);self.expiry.pop(key,None)
        if op=='GET': return self.data.get(key)
        if op=='SET':
            value,*opts=tail
            if 'NX' in opts and key in self.data:return None
            self.data[key]=str(value)
            if 'EX' in opts:self.expiry[key]=self.now+int(opts[opts.index('EX')+1])
            return 'OK'
        if op=='INCR':self.data[key]=str(int(self.data.get(key,0))+1);return int(self.data[key])
        if op=='EXPIRE':self.expiry[key]=self.now+int(tail[0]);return 1
        raise AssertionError(op)
    async def claim(self,key,owner,ttl=90):return await self.command('SET',key,owner,'NX','EX',ttl)=='OK'
    async def release(self,key,owner):
        if await self.command('GET',key)==owner:self.data.pop(key,None)

@pytest.fixture
def store(): return MemoryStore()

@pytest.fixture
def telegram_bot(csv_data, monkeypatch):
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_IDS','42')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fixture-token')
    bot=AsyncMock();bot.send_message.return_value=SimpleNamespace(message_id=100)
    remote=SimpleNamespace(file_size=len(csv_data),download_as_bytearray=AsyncMock(return_value=bytearray(csv_data)))
    bot.get_file.return_value=remote
    return bot

@pytest.fixture
def make_update():
    from telegram import Update
    def make(bot, user=42, chat_type='private', update_id=1, callback=None, name='leads.csv', size=1000):
        message={'message_id':100,'date':0,'chat':{'id':user,'type':chat_type},'from':{'id':user,'first_name':'Test','is_bot':False}}
        if callback is not None:
            data={'update_id':update_id,'callback_query':{'id':str(update_id),'chat_instance':'fixture','from':message['from'],'message':message,'data':callback}}
        else:
            message['document']={'file_id':'fixture-file','file_unique_id':'fixture-id','file_name':name,'file_size':size,'mime_type':'text/csv'}
            data={'update_id':update_id,'message':message}
        return Update.de_json(data,bot)
    return make
