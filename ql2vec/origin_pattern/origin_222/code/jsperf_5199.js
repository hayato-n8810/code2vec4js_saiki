var VAR_1 = new Array(100);
VAR_1.fill(1);
for (var VAR_2 in VAR_1) {
  var VAR_3;
  if (VAR_1.hasOwnProperty(VAR_2)) {
    VAR_3 = VAR_1[VAR_2];
  }
}
