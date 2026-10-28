document.querySelectorAll('.attribute-editor').forEach(function (editor) {
  var catalogue = JSON.parse(document.getElementById('attribute-catalogue').textContent);
  var rows = Array.from(editor.querySelectorAll('.claim-row'));
  var status = editor.querySelector('.attribute-status');
  function field(row, name) { return row.querySelector('[name^="' + name + '"]'); }
  function requirements(row) {
    var type = field(row, 'type').value;
    field(row, 'value').required = !row.hidden && ['piece_count', 'color', 'label_text'].includes(type);
    field(row, 'subject').required = !row.hidden && ['piece_count', 'part_no_damage'].includes(type);
    field(row, 'value').inputMode = type === 'piece_count' ? 'numeric' : 'text';
  }
  function sentence(row) {
    var type = field(row, 'type').value, value = field(row, 'value').value;
    var subject = field(row, 'subject').value;
    if (type === 'piece_count') return value + ' ' + subject + (value === '1' ? '' : 's');
    if (type === 'color') return 'Color: ' + value;
    if (type === 'label_text') return 'Label reads: ' + value;
    if (type === 'part_no_damage') return subject + ' has no visible damage';
    return 'No visible damage';
  }
  function add(attr) {
    var row = rows.find(function (r) { return r.hidden; });
    if (!row) { status.textContent = 'You can add up to ' + rows.length + ' claims. Remove one to add another.'; return; }
    row.hidden = false;
    row.dataset.generated = attr.type === 'uncheckable' ? '' : 'yes';
    ['type', 'subject', 'value'].forEach(function (key) { field(row, key).value = attr[key] || ''; });
    field(row, 'text').value = row.dataset.generated ? sentence(row) : '';
    requirements(row);
    status.textContent = 'Claim added.';
    field(row, row.dataset.generated && ['piece_count', 'color', 'label_text'].includes(attr.type) ? 'value' : 'text').focus();
  }
  editor.querySelector('.category-picker').addEventListener('change', function (event) {
    var chips = editor.querySelector('.attribute-chips'); chips.replaceChildren();
    (catalogue[event.target.value] || []).forEach(function (attr) {
      var button = document.createElement('button');
      button.type = 'button'; button.className = 'secondary attribute-chip'; button.textContent = attr.label;
      button.addEventListener('click', function () { add(attr); }); chips.appendChild(button);
    });
  });
  editor.querySelector('.add-free').addEventListener('click', function () { add({type: 'uncheckable'}); });
  rows.forEach(function (row) {
    requirements(row);
    field(row, 'text').addEventListener('input', function () { row.dataset.generated = ''; });
    ['value', 'subject', 'type'].forEach(function (key) {
      field(row, key).addEventListener('input', function () {
        requirements(row);
        if (row.dataset.generated && field(row, 'type').value !== 'uncheckable') field(row, 'text').value = sentence(row);
      });
    });
    row.querySelector('.remove-claim').addEventListener('click', function () {
      row.hidden = true; row.classList.remove('suggested');
      ['text', 'subject', 'value', 'by'].forEach(function (key) { field(row, key).value = ''; });
      requirements(row);
      status.textContent = 'Claim removed.'; editor.querySelector('.add-free').focus();
    });
  });
});
