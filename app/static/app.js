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
let socket=null,username='',currentRoom='',typingTimer=null,typingUsers=new Set(),lastTypingSent=0;

async function loadRooms(){
  try{const response=await fetch('/rooms');const data=await response.json();
    roomSelect.replaceChildren(...data.rooms.map(room=>{const option=document.createElement('option');option.value=room;option.textContent=room[0].toUpperCase()+room.slice(1);return option;}));
  }catch{showNotice('Could not load rooms. Refresh and try again.');}
}
function showNotice(text){notice.textContent=text;window.clearTimeout(showNotice.timer);showNotice.timer=window.setTimeout(()=>notice.textContent='',4000);}
function setConnected(connected){connection.classList.toggle('online',connected);document.querySelector('#connection-label').textContent=connected?'Connected':'Disconnected';}
function renderUsers(names){
  document.querySelector('#user-count').textContent=names.length;
  usersList.replaceChildren();
  if(!names.length){const empty=document.createElement('li');empty.className='empty-users';empty.textContent='No one is here yet';usersList.append(empty);return;}
  names.forEach(name=>{const item=document.createElement('li'),avatar=document.createElement('span'),label=document.createElement('span');avatar.className='avatar';avatar.textContent=name.slice(0,1).toUpperCase();label.textContent=name+(name===username?' (you)':'');item.append(avatar,label);usersList.append(item);});
}
function addMessage(message){
  const item=document.createElement('li');item.className='message'+(message.username===username?' mine':'');
  const meta=document.createElement('p');meta.className='message-meta';
  const date=new Date(message.created_at);meta.textContent=`${message.username} · ${Number.isNaN(date.getTime())?'':date.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
  const bubble=document.createElement('div');bubble.className='bubble';bubble.textContent=message.text;item.append(meta,bubble);messages.append(item);messages.scrollTop=messages.scrollHeight;
}
function handleEvent(event){
  if(event.type==='history'){messages.replaceChildren();event.messages.forEach(addMessage);}
  else if(event.type==='message')addMessage(event);
  else if(event.type==='presence_update')renderUsers(event.users);
  else if(event.type==='typing'){if(event.is_typing)typingUsers.add(event.username);else typingUsers.delete(event.username);typingLine.textContent=typingUsers.size?`${[...typingUsers].join(', ')} ${typingUsers.size===1?'is':'are'} typing…`:'';}
  else if(event.type==='error')showNotice(event.message);
}
joinForm.addEventListener('submit',event=>{
  event.preventDefault();username=document.querySelector('#username').value.trim();currentRoom=roomSelect.value;
  if(!username)return showNotice('Enter a name to join.');
  if(socket)socket.close();
  const protocol=location.protocol==='https:'?'wss:':'ws:';socket=new WebSocket(`${protocol}//${location.host}/ws`);setConnected(false);
  socket.addEventListener('open',()=>socket.send(JSON.stringify({type:'join_room',username,room:currentRoom})));
  socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.type==='history'){welcome.hidden=true;messages.style.display='flex';composer.hidden=false;document.querySelector('#leave-button').hidden=false;document.querySelector('#room-heading').textContent=currentRoom[0].toUpperCase()+currentRoom.slice(1);setConnected(true);}handleEvent(data);});
  socket.addEventListener('close',()=>{setConnected(false);if(!welcome.hidden){return;}showNotice('Connection closed. Rejoin the room to continue.');composer.hidden=true;document.querySelector('#leave-button').hidden=true;});
  socket.addEventListener('error',()=>showNotice('Could not connect to chat. Try again.'));
});
composer.addEventListener('submit',event=>{event.preventDefault();const text=messageInput.value.trim();if(!text||socket?.readyState!==WebSocket.OPEN)return;socket.send(JSON.stringify({type:'send_message',text}));messageInput.value='';document.querySelector('#char-count').textContent='0 / 500';sendTyping(false);});
messageInput.addEventListener('input',()=>{document.querySelector('#char-count').textContent=`${messageInput.value.length} / 500`;if(socket?.readyState===WebSocket.OPEN){const now=Date.now();if(now-lastTypingSent>900){socket.send(JSON.stringify({type:'typing',is_typing:true}));lastTypingSent=now;}window.clearTimeout(typingTimer);typingTimer=window.setTimeout(()=>sendTyping(false),1200);}});
function sendTyping(isTyping){if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'typing',is_typing:isTyping}));}
document.querySelector('#leave-button').addEventListener('click',()=>{socket?.close();welcome.hidden=false;messages.style.display='none';messages.replaceChildren();composer.hidden=true;document.querySelector('#leave-button').hidden=true;document.querySelector('#room-heading').textContent='Join a room';renderUsers([]);typingUsers.clear();typingLine.textContent='';});
loadRooms();
