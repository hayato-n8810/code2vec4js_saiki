var VAR_1 = {
  KEY_1: 1,
  KEY_2: 2,
  KEY_3: 3,
};
for (prop in VAR_1) {
  if (!VAR_1.hasOwnProperty(prop)) {
    continue;
  }
  prop;
}
