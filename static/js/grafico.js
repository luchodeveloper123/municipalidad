window.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('graficoCortes');
  if (!canvas) return;
  const labels = JSON.parse(canvas.dataset.labels);
  const data   = JSON.parse(canvas.dataset.values);
  const ctx    = canvas.getContext('2d');

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data, backgroundColor: '#3498db' }]
    },
    options: {
      indexAxis: 'x',
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      plugins: { legend: { display: false } },
      responsive: true,
      maintainAspectRatio: false
    }
  });
});

