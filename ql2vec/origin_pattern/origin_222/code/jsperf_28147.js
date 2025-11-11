var VAR_1 = {};
for (var VAR_2 = 0, VAR_3 = 10; VAR_2 < VAR_3; VAR_2 += 1) {
  VAR_1["some_" + VAR_2] = "some_" + VAR_2;
}
var VAR_4;
for (var VAR_5 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_5)) {
    VAR_4 = VAR_1[VAR_5];
  }
}
