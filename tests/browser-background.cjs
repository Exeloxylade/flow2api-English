const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '../browser-extension');
test('background reconnects saved accounts to matching existing tabs and routes each request separately', async () => {
  const sockets = [], executions = [], listeners = {};
  const bindings = {
    a: {account_id: 1, email: 'a@example.com', secret: 'a'.repeat(64), tab_id: 999, port: 8765},
    b: {account_id: 2, email: 'b@example.com', secret: 'b'.repeat(64), tab_id: 8, port: 8765}
  };
  const event = name => ({addListener: fn => {listeners[name] = fn}});
  class Socket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 1; this.sent = []; sockets.push(this); queueMicrotask(() => this.onopen()); }
    send(text) {const value = JSON.parse(text); this.sent.push(value); if (value.secret) queueMicrotask(() => this.onmessage({data: JSON.stringify({type: 'ready'})}));}
    close() {this.readyState = 3; this.onclose?.();}
  }
  const sandbox = {WebSocket: Socket, setTimeout, clearTimeout, setInterval: () => 1, clearInterval: () => {},
    chrome: {
      runtime: {id: 'local-extension', onMessage: event('message'), onStartup: event('startup')},
      alarms: {create: () => {}, onAlarm: event('alarm')},
      storage: {local: {get: async () => ({flowBridgeAccounts: bindings}), set: async () => {}}},
      tabs: {query: async () => [{id: 7}, {id: 8}], onRemoved: event('removed'), onUpdated: event('updated')},
      scripting: {executeScript: async options => {
        const email = {7: 'a@example.com', 8: 'b@example.com'}[options.target.tabId] || '';
        if (!options.args) return [{result: email}];
        executions.push(options.target.tabId);
        return [{result: {success: true, result: {text: 'reply'}}}];
      }}
    }};
  const context = vm.createContext(sandbox);
  sandbox.importScripts = name => vm.runInContext(fs.readFileSync(path.join(root, name), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(root, 'background.js'), 'utf8'), context);
  await new Promise(setImmediate); await new Promise(setImmediate);
  assert.equal(sockets.length, 2);
  const aSocket=sockets.find(s=>s.sent[0].account_id===1);
  const bSocket=sockets.find(s=>s.sent[0].account_id===2);
  await bSocket.onmessage({data: JSON.stringify({type: 'request', req_id: 'b-job', email: 'b@example.com', operation: 'rpc'})});
  await aSocket.onmessage({data: JSON.stringify({type: 'request', req_id: 'a-job', email: 'a@example.com', operation: 'rpc'})});
  assert.deepEqual(executions, [8, 7]);
  aSocket.close();
  await listeners.alarm({name: 'flowBridgeReconnect'});
  await new Promise(setImmediate); await new Promise(setImmediate);
  assert.equal(sockets.length, 3);
  assert.equal(sockets[2].sent[0].account_id, 1);
  for (const socket of sockets) socket.close();
});

test('an unresponsive old pairing cannot hold up a valid saved account on restart', async () => {
  const sockets=[],listeners={};
  const bindings={old:{account_id:1,email:'old@example.com',secret:'a'.repeat(64),tab_id:999,port:8765},current:{account_id:7,email:'current@example.com',secret:'b'.repeat(64),tab_id:8,port:8765}};
  const event=name=>({addListener:fn=>{listeners[name]=fn;}});
  class Socket {
    static OPEN=1;
    constructor(){this.readyState=1;this.sent=[];sockets.push(this);queueMicrotask(()=>this.onopen());}
    send(text){const value=JSON.parse(text);this.sent.push(value);if(value.secret)queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'ready'})}));}
    close(){this.readyState=3;this.onclose?.();}
  }
  const sandbox={WebSocket:Socket,setTimeout:(fn,ms)=>setTimeout(fn,Math.min(ms,30)),clearTimeout,setInterval:()=>1,clearInterval:()=>{},chrome:{
    runtime:{id:'local-extension',onMessage:event('message'),onStartup:event('startup')},
    alarms:{create(){},onAlarm:event('alarm')},
    storage:{local:{get:async()=>({flowBridgeAccounts:bindings})}},
    tabs:{query:async()=>[{id:8,active:true}],onRemoved:event('removed'),onUpdated:event('updated')},
    scripting:{executeScript:options=>options.target.tabId===999?new Promise(()=>{}):Promise.resolve([{result:'current@example.com'}])}
  }};
  const context=vm.createContext(sandbox);
  sandbox.importScripts=name=>vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'background.js'),'utf8'),context);
  await new Promise(setImmediate);await new Promise(setImmediate);
  assert.equal(sockets.length,1);
  assert.equal(sockets[0].sent[0].account_id,7);
  await new Promise(resolve=>setTimeout(resolve,50));
  assert.equal(sockets.length,1);
  sockets[0].close();
});


test('each request reselects a responsive tab for its account and never replays a timed-out submission', async () => {
 const sockets=[],listeners={},executions=[]
 const binding={account_id:7,email:'owner@example.com',secret:'a'.repeat(64),tab_id:7,port:8765}
 let stale=false,hang=false
 const event=name=>({addListener:fn=>{listeners[name]=fn}})
 class Socket {
  static OPEN=1
  constructor(){this.readyState=1;this.sent=[];sockets.push(this);queueMicrotask(()=>this.onopen())}
  send(text){const v=JSON.parse(text);this.sent.push(v);if(v.secret)queueMicrotask(()=>this.onmessage({data:JSON.stringify({type:'ready'})}))}
  close(){this.readyState=3;this.onclose?.()}
 }
 const sandbox={WebSocket:Socket,setTimeout:(fn,ms)=>setTimeout(fn,Math.min(ms,40)),clearTimeout,setInterval:()=>1,clearInterval:()=>{},chrome:{
  runtime:{id:'extension',onMessage:event('message'),onStartup:event('startup')},alarms:{create(){},onAlarm:event('alarm')},
  storage:{local:{get:async()=>({flowBridgeAccounts:{a:binding}}),set:async()=>{}}},
  tabs:{query:async()=>[{id:8,active:true}],onRemoved:event('removed'),onUpdated:event('updated')},
  scripting:{executeScript:options=>{
   if(!options.args)return Promise.resolve([{result:options.target.tabId===7&&stale?'wrong@example.com':'owner@example.com'}])
   executions.push(options.target.tabId)
   return hang?new Promise(()=>{}):Promise.resolve([{result:{success:true,result:{text:'ok'}}}])
  }}
 }}
 const context=vm.createContext(sandbox)
 sandbox.importScripts=name=>vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),context)
 vm.runInContext(fs.readFileSync(path.join(root,'background.js'),'utf8'),context)
 await new Promise(setImmediate);await new Promise(setImmediate)
 const socket=sockets[0];stale=true
 await socket.onmessage({data:JSON.stringify({type:'request',req_id:'first',email:binding.email,operation:'rpc',timeout_ms:30000})})
 assert.deepEqual(executions,[8])
 assert.equal(socket.sent.at(-1).success,true)
 hang=true
 await socket.onmessage({data:JSON.stringify({type:'request',req_id:'second',email:binding.email,operation:'rpc',timeout_ms:30000})})
 assert.deepEqual(executions,[8,8])
 assert.equal(socket.sent.at(-1).error_code,'request_timeout')
 assert.equal(socket.sent.at(-1).req_id,'second')
 socket.close()
})
