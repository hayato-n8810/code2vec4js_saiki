var VAR_1 = [1, 2, 3, 4, 5, 6];
var VAR_2 = 0;
for (key in VAR_1) {
  if (VAR_1.hasOwnProperty(key)) {
    VAR_2++;
  }
}
