var VAR_1 = [];
for (var VAR_2 = 0; VAR_2 < 100000; VAR_2++) {
  VAR_1.push(1);
}
var VAR_3;
for (var VAR_4 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_4)) {
    VAR_3 = VAR_1[VAR_4];
  }
}
