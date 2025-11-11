var VAR_1 = new Array(100000);
var VAR_2;
for (i in VAR_1) {
  if (VAR_1.hasOwnProperty(i)) {
    VAR_2 = VAR_1[i];
  }
}
