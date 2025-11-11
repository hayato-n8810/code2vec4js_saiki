var VAR_1, VAR_2, VAR_3, VAR_4;
VAR_1 = function () {
  VAR_4 = [];
  for (VAR_3 = 0; VAR_3 < 10000; VAR_3++) {
    VAR_4.push(VAR_3);
  }
  return VAR_4;
}.apply(this);
VAR_2 = null;
for (key in VAR_1) {
  if (!VAR_1.hasOwnProperty(key)) continue;
  VAR_2 = VAR_1[key];
}
