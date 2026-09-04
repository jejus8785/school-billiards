let currentMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let counts = {};

const today = new Date();
today.setHours(0,0,0,0);
const maxDate = new Date(today);
maxDate.setFullYear(maxDate.getFullYear() + 10);

// 2026년 9월 7일 ~ 9월 11일은 하루 1팀만 예약 가능
const specialStart = '2026-09-07';
const specialEnd = '2026-09-11';

function maxTeamsForDate(key) {
  if (key >= specialStart && key <= specialEnd) {
    return 1;
  }
  return 2;
}

// 주말(토, 일) 여부를 판별하는 함수 추가
function isWeekend(d) {
  const day = d.getDay();
  return day === 0 || day === 6; // 0: 일요일, 6: 토요일
}

function iso(d) {
  const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), day=String(d.getDate()).padStart(2,'0');
  return `${y}-${m}-${day}`;
}

function showView(id, btn) {
  document.querySelectorAll('.view').forEach(v=>v.classList.add('hidden'));
  document.getElementById(id).classList.remove('hidden');
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
}

async function loadCounts() {
  const r = await fetch('/api/calendar');
  counts = await r.json();
  renderCalendar();
}

function moveMonth(delta) {
  const next = new Date(currentMonth.getFullYear(), currentMonth.getMonth()+delta, 1);
  const min = new Date(today.getFullYear(), today.getMonth(), 1);
  const max = new Date(maxDate.getFullYear(), maxDate.getMonth(), 1);
  if(next < min || next > max) return;
  currentMonth = next;
  renderCalendar();
}

function renderCalendar() {
  document.getElementById('monthTitle').textContent =
    `${currentMonth.getFullYear()}년 ${currentMonth.getMonth()+1}월`;

  const grid = document.getElementById('calendar');
  grid.innerHTML='';

  const first = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1);
  const last = new Date(currentMonth.getFullYear(), currentMonth.getMonth()+1, 0);

  for(let i=0;i<first.getDay();i++) {
    grid.appendChild(document.createElement('div'));
  }

  for(let day=1;day<=last.getDate();day++){
    const d = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day);
    const key=iso(d);
    const count=counts[key]||0;

    // 해당 날짜의 최대 예약 팀 수
    const maxTeams = maxTeamsForDate(key);

    const cell=document.createElement('button');
    cell.className='day';

    let statusText;

    // 주말이거나 기간 외 날짜일 경우 비활성화 처리
    if(d<today || d>maxDate || isWeekend(d)){
      cell.disabled=true;
      cell.classList.add('disabled');
      statusText = isWeekend(d) ? '주말 휴무' : '예약 불가';
    }
    else if(count>=maxTeams){
      cell.classList.add('full');
      statusText='예약 마감';
    }
    else if(count===1){
      cell.classList.add('one');
      statusText='1팀 예약';
    }
    else{
      cell.classList.add('available');
      statusText='예약 가능';
    }

    cell.innerHTML=`<strong>${day}</strong><small>${statusText}</small>`;

    // 주말이 아닐 때만 클릭하여 예약 창 오픈 가능
    if(d>=today && d<=maxDate && !isWeekend(d) && count<maxTeams){
      cell.onclick=()=>openBooking(key);
    }

    grid.appendChild(cell);
  }
}

async function openBooking(key) {
  // 클라이언트 측 한 번 더 주말 차단 방어
  const [y, m, d] = key.split('-').map(Number);
  const dateObj = new Date(y, m - 1, d);
  if (isWeekend(dateObj)) {
    alert('주말에는 예약할 수 없습니다.');
    return;
  }

  const r=await fetch('/api/bookings/'+key);
  const data=await r.json();

  const maxTeams = maxTeamsForDate(key);

  if(data.count>=maxTeams){
    await loadCounts();
    return;
  }

  const title = `${key.slice(0,4)}년 ${Number(key.slice(5,7))}월 ${Number(key.slice(8,10))}일`;

  const extra = [1,2,3].map(i=>
    `<input id="member${i}" inputmode="numeric" maxlength="20" placeholder="추가 학생 ${i} 학번 (선택)">`
  ).join('');

  document.getElementById('modalContent').innerHTML=`
    <div class="eyebrow">BOOKING</div>
    <h2>${title} 당구장 예약</h2>
    <div class="availability-badge">현재 예약: ${data.count} / ${maxTeams}팀</div>
    <form onsubmit="submitBooking(event,'${key}')">
      <label>예약자 이름 <span>*</span></label>
      <input id="name" required placeholder="예약자 이름">

      <label>예약자 학번 <span>*</span></label>
      <input id="studentId" required inputmode="numeric" maxlength="20" placeholder="예약자 학번">

      <label>함께 이용할 학생 학번</label>
      ${extra}

      <p class="form-help">예약자를 포함해 최대 4명까지 가능합니다.</p>

      <button class="primary full" type="submit">예약하기</button>
    </form>`;

  document.getElementById('modal').classList.remove('hidden');
}

async function submitBooking(e,key){
  e.preventDefault();

  const members=[1,2,3]
    .map(i=>document.getElementById('member'+i).value.trim())
    .filter(Boolean);

  const ids=[
    document.getElementById('studentId').value.trim(),
    ...members
  ];

  if(new Set(ids).size!==ids.length){
    alert('같은 학번을 중복해서 입력할 수 없습니다.');
    return;
  }

  const r=await fetch('/api/book',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      date:key,
      name:document.getElementById('name').value.trim(),
      student_id:document.getElementById('studentId').value.trim(),
      members
    })
  });

  const data=await r.json();

  if(!r.ok){
    alert(data.error||'예약에 실패했습니다.');
    await loadCounts();
    return;
  }

  closeModal();
  document.getElementById('modalContent').innerHTML='';
  showCompletion(data.booking);
  await loadCounts();
}

function showCompletion(b){
  document.getElementById('modalContent').innerHTML=`
    <div class="success-icon">✓</div>
    <div class="eyebrow">BOOKING COMPLETE</div>
    <h2>예약이 완료되었습니다.</h2>

    <div class="receipt">
      <div><span>예약 날짜</span><strong>${b.date}</strong></div>
      <div><span>예약 팀</span><strong>${b.team_no}팀</strong></div>
      <div><span>예약자</span><strong>${escapeHtml(b.name)} (${escapeHtml(b.student_id)})</strong></div>
      <div><span>함께 이용</span><strong>${b.members.map(escapeHtml).join(', ')}</strong></div>
    </div>

    <button class="primary full" onclick="closeModal()">확인</button>`;

  document.getElementById('modal').classList.remove('hidden');
}

async function lookupBookings(){
  const id=document.getElementById('lookupId').value.trim();

  if(!id){
    alert('학번을 입력해주세요.');
    return;
  }

  const r=await fetch('/api/lookup',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:id})
  });

  const data=await r.json();
  const box=document.getElementById('lookupResult');

  if(!data.bookings?.length){
    box.innerHTML='<div class="empty">해당 학번이 포함된 예약이 없습니다.</div>';
    return;
  }

  box.innerHTML=data.bookings.map(b=>`
    <div class="booking-card">
      <div class="booking-main">
        <strong>${b.date}</strong>
        <span>${b.team_no}팀</span>
      </div>
      <div>예약자: ${escapeHtml(b.name)} (${escapeHtml(b.student_id)})</div>
      <div class="muted">함께 이용: ${b.members.map(escapeHtml).join(', ')}</div>
    </div>
  `).join('');
}

function closeModal(){
  document.getElementById('modal').classList.add('hidden');
}

document.getElementById('modal').addEventListener('click',e=>{
  if(e.target.id==='modal') closeModal();
});

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g,c=>({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#039;'
  }[c]));
}

loadCounts();
