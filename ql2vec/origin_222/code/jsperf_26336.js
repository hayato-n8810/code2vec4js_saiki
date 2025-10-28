var VAR_1 = {
  KEY_1: 1,
  KEY_2: 1,
  KEY_3: 1,
  KEY_4: 1,
  KEY_5: 1,
  KEY_6: 1,
  KEY_7: 1,
  KEY_8: 1,
};
var VAR_2 = [],
  VAR_3;
for (VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) {
    VAR_2.push(VAR_3, VAR_1[VAR_3]);
  }
}
var VAR_4,
  VAR_5 = 0;
for (VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) {
    VAR_5 += VAR_1[VAR_3];
  }
}
