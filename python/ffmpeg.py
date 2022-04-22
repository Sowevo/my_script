# 用来拼ffmpeg命令,把多个视频合成一个....
row = 6
column = 8
index = 0
width = 250
height = 250

command = 'ffmpeg '
file_list = ''
filter_complex = '-filter_complex "nullsrc=size=' + str(width * row) + 'x' + str(width * column) + ' [base]; '
filter_box = ''
filter_scale = ''
for r in range(0, row):
    for c in range(0, column):
        if index == 0:
            filter_box = filter_box + '[base][scale' + str(index) + '] overlay=shortest=1[t' + str(index) + ']; '
        elif index == row * column - 1:
            filter_box = filter_box + '[t' + str(index - 1) + '][scale' + str(
                index) + '] overlay=shortest=1:x=' + str(r * height) + ':y=' + str(c * width) + ' " out_'+str(width * row)+'.gif'
        else:
            filter_box = filter_box + '[t' + str(index - 1) + '][scale' + str(
                index) + '] overlay=shortest=1:x=' + str(r * height) + ':y=' + str(c * width) + '[t' + str(
                index) + ']; '

        filter_scale = filter_scale + '[' + str(index) + '] setpts=PTS-STARTPTS, scale=' + str(width) + 'x' + str(
            height) + ' [scale' + str(index) + ']; '

        file_list = file_list + '-re -i ' + str(index) + '.webp '
        index = index + 1
print(command + file_list + filter_complex + filter_scale + filter_box)
