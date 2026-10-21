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
let socket=null,username='',currentRoom='',typingTimer=null,reconnectTimer=null;
let shouldReconnect=false,reconnectDelay=1000,typingUsers=new Set(),lastTypingSent=0;

function showNotice(text){notice.textContent=text;window.clearTimeout(showNotice.timer);showNotice.timer=window.setTimeout(()=>notice.textContent='',5000);}
function setConnected(connected){connection.classList.toggle('online',connected);document.querySelector('#connection-label').textContent=connected?'Connected':'Disconnected';}
function renderUsers(names){
  document.querySelector('#user-count').textContent=names.length;usersList.replaceChildren();
  if(!names.length){const empty=document.createElement('li');empty.className='empty-users';empty.textContent='No one is here yet';usersList.append(empty);return;}
  names.forEach(name=>{const item=document.createElement('li'),avatar=document.createElement('span'),label=document.createElement('span');avatar.className='avatar';avatar.textContent=name.slice(0,1).toUpperCase();label.textContent=name+(name===username?' (you)':'');item.append(avatar,label);usersList.append(item);});
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
function sendTyping(isTyping){if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'typing',is_typing:isTyping}));}
function closeRoom(){
  shouldReconnect=false;window.clearTimeout(reconnectTimer);window.clearTimeout(typingTimer);
  const oldSocket=socket;socket=null;if(oldSocket)oldSocket.close();
  setConnected(false);renderUsers([]);typingUsers.clear();typingLine.textContent='';
}
function connect(){
  if(!shouldReconnect)return;
  const scheme=location.protocol==='https:'?'wss:':'ws:';
  const nextSocket=new WebSocket(`${scheme}//${location.host}/ws`);socket=nextSocket;setConnected(false);
  nextSocket.addEventListener('open',()=>{
    if(nextSocket!==socket)return;
    nextSocket.send(JSON.stringify({type:'join_room',username,room:currentRoom}));
  });
  nextSocket.addEventListener('message',event=>{
    if(nextSocket!==socket)return;
    let data;try{data=JSON.parse(event.data);}catch{return;}
    if(data.type==='history'){
      messages.replaceChildren();data.messages.forEach(addMessage);welcome.hidden=true;messages.style.display='flex';
      composer.hidden=false;document.querySelector('#leave-button').hidden=false;
      document.querySelector('#room-heading').textContent=currentRoom[0].toUpperCase()+currentRoom.slice(1);
      setConnected(true);reconnectDelay=1000;
    }else if(data.type==='message')addMessage(data);
    else if(data.type==='presence_update')renderUsers(data.users);
    else if(data.type==='typing'){
      if(data.username===username)return;
      if(data.is_typing)typingUsers.add(data.username);else typingUsers.delete(data.username);
      typingLine.textContent=typingUsers.size?`${[...typingUsers].join(', ')} ${typingUsers.size===1?'is':'are'} typing…`:'';
    }else if(data.type==='ping')nextSocket.send(JSON.stringify({type:'pong'}));
    else if(data.type==='error'){showNotice(data.message);shouldReconnect=false;nextSocket.close();}
  });
  nextSocket.addEventListener('close',()=>{
    if(nextSocket!==socket)return;
    setConnected(false);
    if(shouldReconnect){
      showNotice('Connection interrupted. Reconnecting…');
      reconnectTimer=window.setTimeout(connect,reconnectDelay);reconnectDelay=Math.min(reconnectDelay*2,15000);
    }else if(!welcome.hidden){return;}
    else{composer.hidden=true;document.querySelector('#leave-button').hidden=true;showNotice('Disconnected from chat. Join again to continue.');}
  });
  nextSocket.addEventListener('error',()=>showNotice('Could not connect to chat. Check the WebSocket deployment.'));
}
async function loadRooms(){
  try{
    const response=await fetch('/rooms');if(!response.ok)throw new Error('Room list unavailable');
    const data=await response.json();roomSelect.replaceChildren(...data.rooms.map(room=>{const option=document.createElement('option');option.value=room;option.textContent=room[0].toUpperCase()+room.slice(1);return option;}));
  }catch{showNotice('Could not load rooms. Refresh and try again.');}
}
joinForm.addEventListener('submit',event=>{
  event.preventDefault();username=document.querySelector('#username').value.trim();currentRoom=roomSelect.value;
  if(!username||username.length>20)return showNotice('Name must be between 1 and 20 characters.');
  closeRoom();messages.replaceChildren();shouldReconnect=true;connect();
});
composer.addEventListener('submit',event=>{
  event.preventDefault();const text=messageInput.value.trim();if(!text||socket?.readyState!==WebSocket.OPEN)return;
  socket.send(JSON.stringify({type:'send_message',text}));messageInput.value='';document.querySelector('#char-count').textContent='0 / 500';sendTyping(false);
});
messageInput.addEventListener('input',()=>{
  document.querySelector('#char-count').textContent=`${messageInput.value.length} / 500`;
  if(socket?.readyState===WebSocket.OPEN&&Date.now()-lastTypingSent>800){sendTyping(true);lastTypingSent=Date.now();}
  window.clearTimeout(typingTimer);typingTimer=window.setTimeout(()=>sendTyping(false),1200);
});
document.querySelector('#leave-button').addEventListener('click',()=>{
  closeRoom();welcome.hidden=false;messages.style.display='none';messages.replaceChildren();composer.hidden=true;
  document.querySelector('#leave-button').hidden=true;document.querySelector('#room-heading').textContent='Join a room';
});

loadRooms();
