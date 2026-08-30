let bookings=[];
async function loadAdmin(){
  const r=await fetch('/api/admin/bookings');
  if(r.status===401){location.href='/admin';return;}
  const data=await r.json(); bookings=data.bookings||[];
  updateStats(); renderAdmin();
}
function updateStats(){
  document.getElementById('total').textContent=bookings.length;
  document.getElementById('days').textContent=new Set(bookings.map(b=>b.date)).size;
  document.getElementById('remaining').textContent=bookings.length===0 ? 0 :
    (new Set(bookings.map(b=>b.date)).size*2-bookings.length);
}
function renderAdmin(){
  const q=document.getElementById('adminSearch').value.trim().toLowerCase();
  const list=document.getElementById('adminList');
  const filtered=bookings.filter(b=>
    [b.date,b.name,b.student_id,b.team_no,...b.members].join(' ').toLowerCase().includes(q));
  if(!filtered.length){list.innerHTML='<div class="empty">조건에 맞는 예약이 없습니다.</div>';return;}
  list.innerHTML=filtered.map(b=>`
    <div class="admin-booking">
      <div class="admin-date"><strong>${b.date}</strong><span>${b.team_no}팀</span></div>
      <div class="admin-info">
        <strong>${esc(b.name)}</strong>
        <span>예약자 학번 ${esc(b.student_id)}</span>
        <span>이용 학생: ${b.members.map(esc).join(', ')}</span>
      </div>
      <button class="danger" onclick="cancelBooking(${b.id})">예약 취소</button>
    </div>`).join('');
}
async function cancelBooking(id){
  const b=bookings.find(x=>x.id===id);
  if(!b)return;
  if(!confirm(`${b.date} ${b.team_no}팀 예약을 강제로 취소하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`))return;
  const r=await fetch('/api/admin/bookings/'+id,{method:'DELETE'});
  const data=await r.json();
  if(!r.ok){alert(data.error||'취소에 실패했습니다.');return;}
  await loadAdmin();
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}
loadAdmin();
