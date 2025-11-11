var VAR_1 = {};
for (var VAR_2 = 0; VAR_2 < 150; VAR_2++) {
  VAR_1["key-" + VAR_2] = VAR_2;
}
var VAR_3;
for (var VAR_4 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_4)) {
    VAR_3 = VAR_4;
  }
}
