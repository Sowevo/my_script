from enum import Enum


class Cycle(Enum):
    """付费周期"""
    M_1 = (1, "months", "1月")
    M_2 = (2, "months", "2月")
    M_3 = (3, "months", "3月")
    M_4 = (4, "months", "4月")
    M_5 = (5, "months", "5月")
    M_6 = (6, "months", "6月")
    M_7 = (7, "months", "7月")
    M_8 = (8, "months", "8月")
    M_9 = (9, "months", "9月")
    M_10 = (10, "months", "10月")
    M_11 = (11, "months", "11月")
    M_12 = (12, "months", "12月")
    Y_1 = (1, "years", "1年")
    Y_2 = (2, "years", "2年")
    Y_3 = (3, "years", "3年")
    Y_4 = (4, "years", "4年")
    Y_5 = (5, "years", "5年")
    Y_6 = (6, "years", "6年")
    Y_7 = (7, "years", "7年")
    Y_8 = (8, "years", "8年")
    Y_9 = (9, "years", "9年")
    Y_10 = (10, "years", "10年")
    Q_1 = (1, "quarters", "1季")
    Q_2 = (2, "quarters", "2季")
    Q_3 = (3, "quarters", "3季")
    Q_4 = (4, "quarters", "4季")

    def __init__(self, num, unit, desc):
        self.num = num
        self.unit = unit
        self.desc = desc


def get_longlong_if():
    """生成一个很长很长的if语句"""
    end = "dateAdd(prop(\"开始时间\"),500,\"years\")"
    for cycle in Cycle:
        end = f"if(prop(\"付费周期\")==\"{cycle.desc}\",dateAdd(prop(\"开始时间\"),{cycle.num},\"{cycle.unit}\"),{end})"
    print(end)


if __name__ == '__main__':
    get_longlong_if()
