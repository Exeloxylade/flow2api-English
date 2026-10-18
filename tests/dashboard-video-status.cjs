const {test} = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path')
const html=fs.readFileSync(path.join(__dirname,'../static/manage.html'),'utf8')
function load(name){
 const line=html.split('\n').find(line=>line.trim().startsWith(name+'='))
 const source='const '+line.trim().replace(/,$/,'')+';return '+name
 return new Function('parseLogJson','getLogOperationLabel','extractLogErrorSummary','truncateLogText',source)(raw=>{try{return typeof raw==='string'?JSON.parse(raw):raw}catch{return null}},()=> 'Video',()=>'',text=>text)
}
const status=load('formatLogStatus'), progress=load('formatLogProgress'), outcome=load('formatLogOutcome')
test('unreadable video status is not described as generating or as 45 percent',()=>{
 const log={status_code:102,status_text:'video_status_unknown',progress:45,operation:'generate_video',duration:600,response_body_excerpt:JSON.stringify({poll_timeout_seconds:1500})}
 assert.equal(status(log),'Video status not recognized')
 assert.equal(progress(log),'Unknown')
 assert.equal(outcome(log),'Waited 600s / 1500s timeout · status unreadable')
})
test('pending stage reports waiting and elapsed time; completed results retain real completion',()=>{
 assert.equal(progress({status_text:'video_polling',progress:45}),'Waiting')
 assert.equal(outcome({status_code:102,status_text:'video_polling',operation:'generate_video',duration:22,response_body_excerpt:'broken'}),'Waited 22s')
 assert.equal(progress({status_text:'completed',progress:100}),'100%')
 assert.equal(outcome({status_code:200,operation:'generate_video'}),'Video result returned')
})
