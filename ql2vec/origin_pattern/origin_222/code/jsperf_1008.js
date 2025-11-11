var VAR_1 = {},
  VAR_2 = {},
  VAR_3;
for (VAR_3 = 0; VAR_3 < 10000; VAR_3++) {
  VAR_1["abc_" + VAR_3] = null;
}
for (VAR_3 = 0; VAR_3 < 10; VAR_3++) {
  VAR_2["abc_" + VAR_3] = null;
}
var VAR_4;
for (VAR_4 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_4)) {
    break;
  }
}
