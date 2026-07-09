class SmartInt(int):
    # Суффиксы в порядке возрастания (тысяча → дециллион)
    _SUFFIXES = [
        (10**3,  'к'),
        (10**6,  'млн'),
        (10**9,  'млрд'),
        (10**12, 'трлн'),
        (10**15, 'квдр'),
        (10**18, 'квинт'),
        (10**21, 'секст'),
        (10**24, 'септ'),
        (10**27, 'окт'),
        (10**30, 'нон'),
        (10**33, 'дец'),
    ]

    def __str__(self) -> str:
        num = int(self)
        sign = '-' if num < 0 else ''
        num = abs(num)

        # Числа меньше 1000 выводим как есть
        if num < 1000:
            return f"{sign}{num}"

        # Идём от самого большого суффикса к меньшему
        for threshold, suffix in reversed(self._SUFFIXES):
            if num >= threshold:
                val = num / threshold
                if val.is_integer():
                    return f"{sign}{int(val)}{suffix}"
                else:
                    # Округляем до 1 знака и заменяем точку на запятую
                    formatted = f"{val:.1f}".replace('.', ',')
                    return f"{sign}{formatted}{suffix}"

        # Запасной вариант (никогда не должен выполняться)
        return f"{sign}{num}"

    def __repr__(self) -> str:
        return self.__str__()

    def __format__(self, format_spec: str) -> str:
        # Если явно задан формат (например, :.2f), используем стандартное поведение
        if format_spec:
            return super().__format__(format_spec)
        return self.__str__()