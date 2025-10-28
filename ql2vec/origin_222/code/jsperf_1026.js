var VAR_1 = {},
  VAR_2 = {},
  VAR_3 = {},
  VAR_4;
for (VAR_4 = 0; VAR_4 < 10000; VAR_4++) {
  VAR_1["abc_" + VAR_4] = null;
}
for (VAR_4 = 0; VAR_4 < 10; VAR_4++) {
  VAR_2["abc_" + VAR_4] = null;
}
var VAR_5;
for (VAR_5 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_5)) {
    break;
  }
}
