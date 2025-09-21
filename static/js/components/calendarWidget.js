const WEEKDAYS = ['Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za', 'Zo'];

export class CalendarWidget {
  constructor(root) {
    this.root = root;
    this.today = new Date();
  }

  render() {
    if (!this.root) return;
    const current = new Date();
    const monthName = current.toLocaleString('nl-NL', { month: 'long', year: 'numeric' });
    const firstDay = new Date(current.getFullYear(), current.getMonth(), 1);
    const startDay = (firstDay.getDay() + 6) % 7; // maandag = 0
    const daysInMonth = new Date(current.getFullYear(), current.getMonth() + 1, 0).getDate();

    const header = document.createElement('div');
    header.className = 'calendar__header';
    header.innerHTML = `<span>${monthName}</span><span>${daysInMonth} dagen</span>`;

    const grid = document.createElement('div');
    grid.className = 'calendar__grid';

    WEEKDAYS.forEach((day) => {
      const span = document.createElement('span');
      span.textContent = day;
      span.style.fontWeight = '600';
      grid.appendChild(span);
    });

    for (let i = 0; i < startDay; i += 1) {
      grid.appendChild(document.createElement('span'));
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const span = document.createElement('span');
      span.textContent = day;
      const isToday = day === current.getDate();
      if (isToday) {
        span.classList.add('is-today');
      }
      grid.appendChild(span);
    }

    this.root.innerHTML = '';
    this.root.appendChild(header);
    this.root.appendChild(grid);
  }
}
