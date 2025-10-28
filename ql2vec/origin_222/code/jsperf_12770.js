var VAR_1 = ["a", "b", "c", "d", "e"],
  VAR_2;
for (var VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) {
    VAR_2 = VAR_1[VAR_3];
  }
}
