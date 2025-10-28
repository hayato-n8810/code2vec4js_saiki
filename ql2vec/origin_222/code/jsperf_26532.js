var VAR_1 = {
  KEY_1: 1,
  KEY_2: 2,
  KEY_3: 3,
};
var VAR_2 = 0;
for (var VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) {
    VAR_2++;
  }
}
