import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const roomSelect=document.querySelector('#room');
const joinForm=document.querySelector('#join-form');
const welcome=document.querySelector('#welcome');
const messages=document.querySelector('#messages');
const composer=document.querySelector('#message-form');
const messageInput=document.querySelector('#message-input');
const notice=document.querySelector('#notice');
const typingLine=document.querySelector('#typing-line');
const usersList=document.querySelector('#users');
const connection=document.querySelector('.connection');
const rooms=['general','football','music'];
let supabase=null,channel=null,username='',currentRoom='',typingTimer=null;
let typingUsers=new Set(),lastTypingSent=0;

function showNotice(text){notice.textContent=text;window.clearTimeout(showNotice.timer);showNotice.timer=window.setTimeout(()=>notice.textContent='',4000);}
function setConnected(connected){connection.classList.toggle('online',connected);document.querySelector('#connection-label').textContent=connected?'Connected':'Disconnected';}
function renderUsers(names){
  document.querySelector('#user-count').textContent=names.length;usersList.replaceChildren();
  if(!names.length){const empty=document.createElement('li');empty.className='empty-users';empty.textContent='No one is here yet';usersList.append(empty);return;}
  names.forEach(name=>{const item=document.createElement('li'),avatar=document.createElement('span'),label=document.createElement('span');avatar.className='avatar';avatar.textContent=name.slice(0,1).toUpperCase();label.textContent=name+(name===username?' (you)':'');item.append(avatar,label);usersList.append(item);});
}
function syncPresence(){
  const state=channel?.presenceState()||{};
  const names=Object.values(state).flat().map(entry=>entry.username).filter(Boolean);
  renderUsers([...new Set(names)].sort((a,b)=>a.localeCompare(b)));
}
function addMessage(message){
  if(document.querySelector(`[data-message-id="${CSS.escape(String(message.id))}"]`))return;
  const item=document.createElement('li');item.className='message'+(message.username===username?' mine':'');item.dataset.messageId=message.id;
  const meta=document.createElement('p');meta.className='message-meta';
  const date=new Date(message.created_at);meta.textContent=`${message.username} · ${Number.isNaN(date.getTime())?'':date.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
  const bubble=document.createElement('div');bubble.className='bubble';bubble.textContent=message.text;item.append(meta,bubble);messages.append(item);
  [...messages.children].sort((first,second)=>Number(first.dataset.messageId)-Number(second.dataset.messageId)).forEach(node=>messages.append(node));
  messages.scrollTop=messages.scrollHeight;
}
async function sendTyping(isTyping){
  if(channel)await channel.send({type:'broadcast',event:'typing',payload:{username,is_typing:isTyping}});
}
async function leaveRoom(){
  const oldChannel=channel;channel=null;typingUsers.clear();typingLine.textContent='';
  if(oldChannel&&supabase){await oldChannel.untrack();await supabase.removeChannel(oldChannel);}
  setConnected(false);renderUsers([]);
}
async function joinRoom(event){
  event.preventDefault();
  username=document.querySelector('#username').value.trim();currentRoom=roomSelect.value;
  if(!username||username.length>20)return showNotice('Name must be between 1 and 20 characters.');
  if(!supabase)return showNotice('Chat setup is incomplete. Check the deployment environment variables.');
  await leaveRoom();messages.replaceChildren();typingUsers.clear();setConnected(false);
  channel=supabase.channel(`room:${currentRoom}`,{config:{presence:{key:crypto.randomUUID()},broadcast:{self:false}}})
    .on('presence',{event:'sync'},syncPresence)
    .on('broadcast',{event:'typing'},({payload})=>{
      if(payload.username===username)return;
      if(payload.is_typing)typingUsers.add(payload.username);else typingUsers.delete(payload.username);
      typingLine.textContent=typingUsers.size?`${[...typingUsers].join(', ')} ${typingUsers.size===1?'is':'are'} typing…`:'';
    })
    .on('postgres_changes',{event:'INSERT',schema:'public',table:'messages',filter:`room=eq.${currentRoom}`},({new:message})=>addMessage(message));
  const activeChannel=channel;
  activeChannel.subscribe(async status=>{
    if(activeChannel!==channel)return;
    if(status==='SUBSCRIBED'){
      const names=Object.values(activeChannel.presenceState()).flat().map(entry=>entry.username).filter(Boolean);
      if(names.some(name=>name.toLocaleLowerCase()===username.toLocaleLowerCase())){
        showNotice('That name is already in this room.');await leaveRoom();return;
      }
      const tracked=await activeChannel.track({username,online_at:new Date().toISOString()});
      if(tracked==='ok'){
        welcome.hidden=true;messages.style.display='flex';composer.hidden=false;document.querySelector('#leave-button').hidden=false;
        document.querySelector('#room-heading').textContent=currentRoom[0].toUpperCase()+currentRoom.slice(1);setConnected(true);
        const {data,error}=await supabase.from('messages').select('id,room,username,text,created_at').eq('room',currentRoom).order('id',{ascending:false}).limit(50);
        if(error)showNotice('Could not load message history. Check the Supabase table policies.');
        else data.reverse().forEach(addMessage);
      }else{showNotice('Could not join presence for this room.');await leaveRoom();}
    }else if(['CHANNEL_ERROR','TIMED_OUT','CLOSED'].includes(status)){
      setConnected(false);showNotice('Realtime connection failed. Check Supabase Realtime settings.');
    }
  });
}

rooms.forEach(room=>{const option=document.createElement('option');option.value=room;option.textContent=room[0].toUpperCase()+room.slice(1);roomSelect.append(option);});
joinForm.addEventListener('submit',joinRoom);
composer.addEventListener('submit',async event=>{
  event.preventDefault();const text=messageInput.value.trim();if(!text||!channel)return;
  const {error}=await supabase.from('messages').insert({room:currentRoom,username,text});
  if(error)showNotice(error.message.includes('messages')?'Message rejected. Check the database policies.':'Could not send message. Try again.');
  else{messageInput.value='';document.querySelector('#char-count').textContent='0 / 500';window.clearTimeout(typingTimer);sendTyping(false);}
});
messageInput.addEventListener('input',()=>{
  document.querySelector('#char-count').textContent=`${messageInput.value.length} / 500`;
  if(channel&&Date.now()-lastTypingSent>800){sendTyping(true);lastTypingSent=Date.now();}
  window.clearTimeout(typingTimer);typingTimer=window.setTimeout(()=>sendTyping(false),1200);
});
document.querySelector('#leave-button').addEventListener('click',async()=>{
  await leaveRoom();welcome.hidden=false;messages.style.display='none';messages.replaceChildren();composer.hidden=true;
  document.querySelector('#leave-button').hidden=true;document.querySelector('#room-heading').textContent='Join a room';
});

try{
  const response=await fetch('/api/config');
  if(!response.ok)throw new Error('Missing Supabase configuration');
  const config=await response.json();supabase=createClient(config.supabaseUrl,config.supabaseKey);
}catch{showNotice('Chat is not configured yet. Add the Supabase URL and publishable key in Vercel settings.');}
