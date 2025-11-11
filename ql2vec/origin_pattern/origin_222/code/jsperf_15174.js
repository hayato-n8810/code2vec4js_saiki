var VAR_1 = {
  KEY_1: 5,
  KEY_2: 10,
  KEY_3: 4,
  KEY_4: [1, 2, 3, 4, 5],
  KEY_5: { KEY_6: 5 },
  KEY_7: false,
  KEY_8: undefined,
};
for (var VAR_2 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_2)) {
    VAR_1[VAR_2];
  }
}
