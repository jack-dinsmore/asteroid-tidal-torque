import os, sys
from PIL import Image, ImageFont, ImageDraw

PATH = "minimizer"
RUNS = 0
CORNER = 1
PARAMS = 2
REDCHI = 3
font = ImageFont.truetype("/usr/share/fonts/truetype/cmu/cmunrm.ttf", 20)

dirs = next(os.walk(PATH))[1]
for d in dirs:
    hindex = 0
    while True:
        try:
            images = [Image.open(PATH+'/'+d+'/'+d+'-'+str(hindex)+x) for x in ['-compare.png', '-corner.png', '-params.png', '-redchi.png']]
        except:
            if hindex == 0:
                print("Could not find files for {}".format(d))
            break

        widths, heights = zip(*(i.size for i in images))

        bi_height = max(heights[PARAMS], heights[REDCHI])
        bi_width = widths[PARAMS] + widths[REDCHI]

        im_width = widths[CORNER] + max(widths[RUNS], bi_width)
        im_height = max(heights[CORNER], heights[RUNS] + bi_height)

        new_im = Image.new('RGB', (im_width, im_height), color=(255, 255, 255))

        new_im.paste(images[CORNER], (0, int((im_height - heights[CORNER]) / 2)))
        new_im.paste(images[RUNS],
            (widths[CORNER] + int((im_width - widths[CORNER] - widths[RUNS]) / 2),
            int((im_height - heights[RUNS] - bi_height) / 2)))
        new_im.paste(images[PARAMS],
            (widths[CORNER] + int((im_width - widths[CORNER] - bi_width) / 2),
            heights[RUNS] + int((im_height - heights[RUNS] - bi_height) / 2)))
        new_im.paste(images[REDCHI],
            (widths[PARAMS] + widths[CORNER] + int((im_width - widths[CORNER] - bi_width) / 2),
            heights[RUNS] + int((im_height - heights[RUNS] - bi_height) / 2)))

        f = open(PATH+"/"+d+"/"+d+".dat", 'r')
        max_j, max_l = f.readline().split(", ")
        max_j, max_l = (int(max_j), int(max_l))
        cadence = int(f.readline())
        impact_parameter = int(f.readline())
        radius = float(f.readline())
        speed = float(f.readline())
        spin = [float(x) for x in f.readline().split(',')]
        jlms = [float(x) for x in f.readline().split(',')]
        theta_true = [float(x) for x in f.readline().split(',')]
        theta_high = [float(x) for x in f.readline().split(',')]
        theta_low = [float(x) for x in f.readline().split(',')]
        sigma = float(f.readline())
        f.close()

        f = open(PATH+"/"+d+"/"+d+"-"+str(hindex)+"-results.txt", 'r')
        theta_median = []
        theta_plus = []
        theta_minus = []
        for line in f.readlines():
            if line == "": continue
            median, plus, minus, _ = line.split(": ")[1].split(' ')
            theta_median.append('%s' % float('%.4g' % float(median)))
            theta_plus.append('%s' % float('%.4g' % float(plus[:-1]))) # Remove the terminal comma
            theta_minus.append('%s' % float('%.4g' % -float(minus[:-1])))
        f.close()

        draw = ImageDraw.Draw(new_im)
        text = ""
        #text += "Cadence: {}\n".format(cadence)
        #text += "Speed: {}\t Impact parameter: {} Earth radii\n".format(speed, impact_parameter)
        #text += "Spin: {}\n".format(spin)
        #text += "Jlms: {}\n".format(jlms)
        text += "True theta: {}\n".format(theta_true)
        text += "Theta high: {}\n".format(theta_high)
        text += "Theta low: {}\n\n".format(theta_low)
        text += "Theta median: {}\n".format(theta_median)
        text += "Theta -sigma: {}\n".format(theta_minus)
        text += "Theta +sigma: {}".format(theta_plus)

        draw.text((widths[CORNER]/2+40, 40), text, font=font, align="left", fill='black')
        new_im.save(PATH+'/'+d+"/"+d+"-"+str(hindex)+"-all.png")

        for x in ['-compare.png', '-corner.png', '-params.png', '-redchi.png', '-results.txt']:
            os.remove(PATH+'/'+d+'/'+d+"-"+str(hindex)+x)

        hindex += 1
