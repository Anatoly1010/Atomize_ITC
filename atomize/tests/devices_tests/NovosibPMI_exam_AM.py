import math

# sample.py
import ctypes
import os
import time
import timeit
import numpy as np
# Пытаемся найти .so-файл в том же каталоге, что и этот файл
print ("Program start")


#_file_helperLib = 'libConfigGIM.so'
_file_helperLib = 'GIM.so'
_file_brdLib = 'libNvsbLib.so'
_file_DataCheckerLib = 'libdataChecker.so'
print(os.path.split(__file__))
print(os.path.split(_file_helperLib))

_path = '/home/fel2/sources/Atomize_ITC/libs/' + _file_helperLib
os.path.join(*(os.path.split(__file__)[:-1] + (_file_helperLib,)))
formGIMLib = ctypes.cdll.LoadLibrary(_path)
print("formGIMLib opened")

#_path = os.path.join(*(os.path.split(__file__)[:-1] + (_file_brdLib,)))
_path = '/home/fel2/sources/Atomize_ITC/libs/' + _file_brdLib
#print(_path)
brdLib = ctypes.cdll.LoadLibrary(_path)
print("brdLib opened")

_path = '/home/fel2/sources/Atomize_ITC/libs/' + _file_DataCheckerLib
#_path = os.path.join(*(os.path.split(__file__)[:-1] + (_file_DataCheckerLib,)))

dataCheckerLib = ctypes.cdll.LoadLibrary(_path)
print("dataCheckerLib opened")



def pack2read64(a,b):
    get_bin = lambda x, n: format(x, 'b').zfill(n)
    size , d = b, a
    print()
    rp = [get_bin(int(d[i]),64) for  i in range(int(size)) ]
    rp = [rp[i*4] for i in range(int(len(rp)/4))]
    [print('{:>10}'.format(round(1*int(i[:48],2),2)),i[48:53],i[53:]) for i in rp]
    print()

def pack2read(a,b):
    get_bin = lambda x, n: format(x, 'b').zfill(n)
    size , d = b, a
    print()
    rp = [get_bin(int(d[i]),32) for  i in range(int(size)) ]
    rp = [rp[i*8+1]+rp[i*8] for i in range(int(len(rp)/8))]
    [print('{:>10}'.format(round(1*int(i[:48],2),2)),i[48:53],i[53:]) for i in rp]
    print()

def pack2read_direct(a,b):
    get_bin = lambda x, n: format(x, 'b').zfill(n)
    size , d = b, a
    print()
    rp = [get_bin(int(d[i]),32) for  i in range(int(size)) ]
    rp = [rp[i*8]+rp[i*8+1] for i in range(int(len(rp)/8))]
    [print('{:>10}'.format(round(1*int(i[:32],2),2)),i[32:37],i[37:48]) for i in rp]
    print()

def reverse_bytes(byte_obj):
    reversed_bytes = byte_obj[::-1]
    return int( reversed_bytes[:-2], 2 )


def gen_pointer(ptype='64'):
    if ptype == '64':
        #Standard 64
        p1 = (1 << 2) + (125 << 16)
        p2 = (1 << 15) + (80000 << 16)

        a1_ar = [ p1 , 0, 0, 0]
        a2_ar = [ p2 , 0, 0, 0]

        x = a1_ar + a2_ar
        #print(x)

        y = (ctypes.c_int64*8)(*x)
        #print(y)
        yLen = len(x)

        ##pack2read64(y, yLen)
        return y, yLen

    elif ptype == '32':
        #Standard 32
        p1 = (1 << 2) + (125 << 16)
        p2 = (1 << 15) + (312375 << 16)

        p11 = p1 << 16
        p21 = p2 << 16
        
        a1_ar = [ p11 >> 32, p11 - ((p11 >> 32) << 32), 0, 0, 0, 0, 0, 0]
        a2_ar = [ p21 >> 32, p21 - ((p21 >> 32) << 32), 0, 0, 0, 0, 0, 0]

        x = a1_ar + a2_ar
        #print(x)

        y = (ctypes.c_int32*16)(*x)
        #print(y)

        yLen = len(x)
        ##pack2read_direct(y, yLen)

        return y, yLen

    elif ptype == '32r':
        ## Reversed Order
        p1 = (1 << 2) + (312 << 16)
        p2 = (1 << 2) + (1 << 1) + (1250 << 16)
        p3 = (1 << 2) + (313 << 16)
        p4 = (1 << 15) + (29375 << 16)

        p11 = p1
        p21 = p2
        p31 = p3
        p41 = p4

        p11_64 = reverse_bytes(format(p11, '#066b'))
        p21_64 = reverse_bytes(format(p21, '#066b'))
        p21_64 = reverse_bytes(format(p31, '#066b'))
        p21_64 = reverse_bytes(format(p41, '#066b'))

        a1_ar = [ p11 - ((p11 >> 32) << 32), p11 >> 32, 0, 0, 0, 0, 0, 0]
        a2_ar = [ p21 - ((p21 >> 32) << 32), p21 >> 32, 0, 0, 0, 0, 0, 0]
        a3_ar = [ p31 - ((p31 >> 32) << 32), p31 >> 32, 0, 0, 0, 0, 0, 0]
        a4_ar = [ p41 - ((p41 >> 32) << 32), p41 >> 32, 0, 0, 0, 0, 0, 0]

        x = a1_ar + a2_ar + a3_ar + a4_ar
        print(x)

        y = (ctypes.c_int32*32)(*x)
        #print(y)
        yLen = len(x)
        #pack2read(y, yLen)
        
        return y, yLen



formGIMLib.newConfigGIM.restype = ctypes.c_void_p
formGIMLib.delConfigGIM.restype = ctypes.c_int32
formGIMLib.delConfigGIM.argtypes = [ctypes.c_void_p]

formGIMLib.addImpParamsIP_py.restype = ctypes.c_int32 #(IPconfigFile* classInp, uint32_t nChanNo, uint64_t nStartPoint, uint64_t nStopPoint );
formGIMLib.addImpParamsIP_py.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

formGIMLib.get1stChanImpLenPMI_py.restype = ctypes.c_int32
formGIMLib.get1stChanImpLenPMI_py.argtypes = [ctypes.c_int32]

brdLib.initBrd.restype = ctypes.c_int32
brdLib.closeBrd.restype = ctypes.c_int32
brdLib.getDAC_ChanNum.restype = ctypes.c_int32
brdLib.write_DAC_data.restype = ctypes.c_int32
brdLib.write_DAC_data.argtypes = [ctypes.POINTER(ctypes.c_int16), ctypes.c_int32]
brdLib.getStrmBufSizeb.restype = ctypes.c_int32

brdLib.setZero_GIM.restype = ctypes.c_int32
brdLib.rst_GIM.restype = ctypes.c_int32
brdLib.setSync_GIM.restype = ctypes.c_int32
brdLib.setSync_GIM.argtypes = [ctypes.c_int32]
brdLib.rstDACFIFO_GIM.restype = ctypes.c_int32
brdLib.rstDACFIFO_GIM.argtypes = [ctypes.c_int32]
brdLib.setDACWriteEnable_GIM.restype = ctypes.c_int32
brdLib.setDACWriteEnable_GIM.argtypes = [ctypes.c_int32, ctypes.c_int32]
brdLib.rstFIFO_GIM.restype = ctypes.c_int32
brdLib.rstFIFO_GIM.argtypes = [ctypes.c_int32]
brdLib.setWriteEnable_GIM.restype = ctypes.c_int32
brdLib.setWriteEnable_GIM.argtypes = [ctypes.c_int32, ctypes.c_int32]
brdLib.setFIFOCnt_GIM.restype = ctypes.c_int32
brdLib.setFIFOCnt_GIM.argtypes = [ctypes.c_int32, ctypes.c_int32]
brdLib.set1stChanImpLen_GIM.restype = ctypes.c_int32
brdLib.set1stChanImpLen_GIM.argtypes = [ctypes.c_int32, ctypes.c_int32]
brdLib.setId_GIM.restype = ctypes.c_int32
brdLib.setId_GIM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
brdLib.setGIM_mode.restype = ctypes.c_int32
brdLib.setGIM_mode.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
brdLib.setDACEnable_GIM.restype = ctypes.c_int32
brdLib.setDACEnable_GIM.argtypes = [ctypes.c_int32]
brdLib.setEnable_GIM.restype = ctypes.c_int32
brdLib.setEnable_GIM.argtypes = [ctypes.c_int32]
brdLib.setSelect_GIM.restype = ctypes.c_int32
brdLib.setSelect_GIM.argtypes = [ctypes.c_int32]
brdLib.setSwitchEn_GIM.restype = ctypes.c_int32
brdLib.setSwitchEn_GIM.argtypes = [ctypes.c_int32]
brdLib.getGIM_swComp_GIM_status.restype = ctypes.c_int32

brdLib.writeIP.restype = ctypes.c_int32

#############################
#brdLib.writeIP.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32]
brdLib.writeIP.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32]

brdLib.DAC_Start.restype = ctypes.c_int32
brdLib.AdcStreamStart.restype = ctypes.c_int32
brdLib.AdcStreamGetBufState.restype = ctypes.c_int32
brdLib.AdcStreamGetBuf_buf.restype = ctypes.c_int32
brdLib.AdcStreamGetBuf_buf.argtypes = [ctypes.POINTER(ctypes.c_int32)]
brdLib.AdcStreamGetBuf_ptr.restype = ctypes.POINTER(ctypes.c_int32)
brdLib.getStreamBufNum.restype = ctypes.c_int32



formGIMLib.genPMIipBufs_py.restype = ctypes.c_int32
formGIMLib.genPMIipBufs_py.argtypes = [ctypes.c_int32]
formGIMLib.getPMI_PIbufSize_py.restype = ctypes.c_int32
formGIMLib.getPMI_PIbufSize_py.argtypes = [ctypes.c_int32]
formGIMLib.getPMI_PIbuf_py.restype = ctypes.c_int32
formGIMLib.getPMI_PIbuf_py.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32, ctypes.c_int32]
formGIMLib.cleanUp_py.restype = ctypes.c_int32

formGIMLib.getDAC_ChanImpLen_py.restype = ctypes.c_int32
formGIMLib.getDAC_ChanImpLen_py.argtypes = [ctypes.c_int32, ctypes.c_int32]

dataCheckerLib.newDataChecker.restype = ctypes.c_int32
dataCheckerLib.checkData.restype = ctypes.c_int32
dataCheckerLib.checkData.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32]
dataCheckerLib.cleanUp.restype = ctypes.c_int32

print("funcs loaded")


pmiLoopsNum = 5
gimSum = 0
inlibBufsNum = formGIMLib.genPMIipBufs_py(pmiLoopsNum)
print("formed PMI bufs")

massData = [] #добавляем массив массивов
massDataSizew = []
anAdcLen = []

##for ii in range (pmiLoopsNum):
##    bufSizew = formGIMLib.getPMI_PIbufSize_py(ii)
##    #print( "buf size = ", bufSizew)
##    dataBuf = (ctypes.c_int*bufSizew)()
##    dataSizeb = formGIMLib.getPMI_PIbuf_py(dataBuf, ii, bufSizew)
##    massData.append(dataBuf)
##    massDataSizew.append(bufSizew)

#for ii in range (pmiLoopsNum):
#   tmpLen = formGIMLib.get1stChanImpLenPMI_py(ii)
#	anAdcLen.append(tmpLen)

#
# Start to work with BRD
#
# initing board 
initRet = brdLib.initBrd()
print("initRet = ", initRet)

ret = brdLib.setZero_GIM()
ret = brdLib.rst_GIM()
ret = brdLib.setSync_GIM(0)

nIP_No = 0
#запись ИП в плис

for i in range(4):

    brdLib.setSwitchEn_GIM(0)
    brdLib.rstFIFO_GIM((nIP_No&1))
    brdLib.setWriteEnable_GIM((nIP_No&1), 1)
    brdLib.setFIFOCnt_GIM((nIP_No&1), 10) #количество повторений

    #x=massData[0][:64]
    #x2 = [8192509, 0, 0, 0, 0, 0, 0, 0, 20447360, 0, 0, 0, 0, 0, 0, 0, 849641600, 1, 0, 0, 0, 0, 0, 0]
    #y = (ctypes.c_int32*64)(*x)
    #y2 = (ctypes.c_int32*24)(*x2)
    #print(y2)


    y, yLen = gen_pointer(ptype='32r')

    #brdLib.writeIP(massData[0], massDataSizew[0])
    #brdLib.writeIP(y2, ctypes.c_int32(24))
    brdLib.writeIP(y, ctypes.c_int32(32))

    #brdLib.set1stChanImpLen_GIM((nIP_No&1), anAdcLen[nIP_No])
    brdLib.set1stChanImpLen_GIM((nIP_No&1), 0)
    brdLib.setWriteEnable_GIM((nIP_No&1), 0)
    brdLib.setId_GIM(nIP_No&1, nIP_No+100, 0)
    brdLib.setGIM_mode((nIP_No&1), 0, gimSum)

    brdLib.setSelect_GIM((nIP_No&1))
    brdLib.setSwitchEn_GIM(1)

    brdLib.setEnable_GIM(1)

    if nIP_No == 0:
        # старт сбора данных
        brdLib.AdcStreamStart() #старт потока данных
    else:
        pass
    
    while True:
        if brdLib.getGIM_swComp_GIM_status() == 0:
            pass
        else:
            #time.sleep(10)
            brdLib.setEnable_GIM(0)
            break

    nIP_No = nIP_No + 1


#print()

#new_list=massData[0][:80]
#print('massData: ')
#print(new_list)
#print()

#print(massData[0], massDataSizew[0])
pack2read(y, 32)
#pack2read(y, 64)

dataCheckerLib.cleanUp()
brdLib.closeBrd()

print ("End of work")

